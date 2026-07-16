from odoo import fields, http, _
from odoo.http import request,Response
from odoo.http import request, content_disposition
from dateutil.relativedelta import relativedelta
from datetime import datetime
import json
import logging
import os
import time
from pprint import pprint
from . import validations
from odoo import api, models
from odoo.http import request
import base64
import requests
import mimetypes
from odoo import SUPERUSER_ID

_logger = logging.getLogger(__name__)


class AccountMove(http.Controller):

    @staticmethod
    def _safe_rollback(cr):
        """Rollback without crashing if connection/cursor already closed."""
        try:
            cr.rollback()
        except Exception as rb_err:
            _logger.warning("Could not rollback (connection may be closed): %s", rb_err)

    @staticmethod
    def _is_cursor_closed(cr):
        """Check if the DB cursor/connection is still usable."""
        try:
            cr.execute("SELECT 1")
            return False
        except Exception:
            return True

    @staticmethod
    def _reraise_if_concurrent_conflict(error_str):
        """
        Call this from inside an `except Exception as e:` block, passing
        str(e). If the error is a PostgreSQL serialization/deadlock/lock
        conflict (two requests touching the same row at the same time),
        re-raises it so an outer retry wrapper can catch it and try again.
        Any other kind of error is left alone (caller's normal handling
        for it continues as before).
        """
        if AccountMove._is_concurrency_conflict(error_str):
            raise Exception(error_str)

    @staticmethod
    def _is_concurrency_conflict(error_str):
        """
        Single source of truth for recognizing a 'two requests touched the
        same row at once' error, whichever of PostgreSQL's several wordings
        it shows up as:
          - "could not serialize access due to concurrent update"
            → SERIALIZABLE isolation conflict
          - "deadlock detected"
            → two transactions waiting on each other
          - "could not obtain lock on row ... NOWAIT"
            → our own explicit FOR UPDATE NOWAIT row lock was already held
              by another in-flight request
        All three mean the same thing from the caller's point of view:
        briefly back off and retry, don't treat it as a real failure.
        """
        return (
            'could not serialize access due to concurrent update' in error_str
            or 'deadlock detected' in error_str
            or 'could not obtain lock on row' in error_str
        )


    @staticmethod
    def _clean_gstin(vat):
        """
        Validate and return GSTIN if valid, else return empty string.
        GSTIN format: 2 digits + 5 letters + 4 digits + 1 letter + Z + 1 letter = 15 chars
        Example: 29AABCV2840F1ZW
        Returns the VAT as-is if valid, empty string if invalid (to avoid Odoo rejection).
        """
        import re
        if not vat:
            return ''
        vat = vat.strip().upper()
        # Standard GSTIN pattern
        pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
        if re.match(pattern, vat):
            return vat
        # Invalid GSTIN — log and return empty so invoice still gets created
        _logger.warning(
            "Invalid GSTIN '%s' — skipping VAT field to allow invoice creation", vat)
        return ''


    
    def _resolve_tally_tax(self, tax_item, company):
        import re

        tax_item_clean = tax_item.strip()
        tax_upper = tax_item_clean.upper()

        # ── Step 1: Detect tax type from Tally string ──────────────────────────

        # IGST indicators from Tally
        is_igst = any(kw in tax_upper for kw in [
            'IGST', 'INTEGRATED', 'INTEGRATED TAX', 'INTER STATE', 'INTER-STATE'
        ])

        # Exempt / Nil / Non-GST indicators
        is_exempt = any(kw in tax_upper for kw in [
            'EXEMPT', 'NIL', 'NON GST', 'NON-GST', 'NONGST', 'NGST', 'NOT APPLICABLE'
        ])

        # ── Step 2: Extract percentage from anywhere in the string ────────────
        # Primary match: handles '18%', '@18%', 'GST@18%', 'GST 18 %', '18 %', '18.0%'
        match = re.search(r'@?\s*(\d+(?:\.\d+)?)\s*%', tax_item_clean)

        # Fallback: Tally sometimes sends bare numbers like '18', 'GST 18', 'IGST 18', '@18'
        if not match:
            match = re.search(r'(?:^|[\s@])(\d+(?:\.\d+)?)\s*$', tax_item_clean)
            if match:
                _logger.info(
                    "Tally tax '%s' → no '%%' symbol found, extracted bare number '%s'",
                    tax_item, match.group(1)
                )

        # ── Step 3: Handle exempt / nil / zero cases ──────────────────────────
        if is_exempt or (match and match.group(1) == '0'):
            candidate_names = ['0% Exempt', '0%', '0% NGST', '0% IGST S']
            _logger.info(
                "Tally tax '%s' → detected as exempt/nil → trying: %s",
                tax_item, candidate_names
            )

        elif not match:
            # No percentage found at all — try direct exact match as last resort
            _logger.warning(
                "Tally tax '%s' → no percentage found, trying direct match", tax_item
            )
            tax = request.env['account.tax'].sudo().search([
                ('name', '=', tax_item_clean),
                ('company_id', '=', company.id),
                ('type_tax_use', '=', 'sale')
            ], limit=1)
            if tax:
                _logger.info(
                    "Tally tax '%s' → direct matched '%s' (id:%s)",
                    tax_item, tax.name, tax.id
                )
                return [tax.id], None
            return [], {
                'success': False,
                'message': (
                    f"Tax '{tax_item}' from Tally could not be parsed. "
                    f"No percentage found and no direct match in Odoo."
                ),
                'status': 400
            }

        else:
            # We have a percentage — build candidate Odoo names
            percent = match.group(1).rstrip('0').rstrip('.') if '.' in match.group(1) else match.group(1)
            # Normalize: '18.0' → '18', '5.0' → '5', '12.5' stays '12.5'
            try:
                percent = str(int(float(percent))) if float(percent) == int(float(percent)) else percent
            except Exception:
                pass

            if is_igst:
                candidate_names = [
                    f"{percent}% IGST S",       # e.g. '18% IGST S'
                    f"{percent}% IGST",         # e.g. '18% IGST'
                    f"IGST {percent}%",         # e.g. 'IGST 18%'
                    f"IGST@{percent}%",         # e.g. 'IGST@18%'
                ]
            else:
                # Plain % or GST % from Tally → GST in Odoo (CGST+SGST group)
                candidate_names = [
                    f"{percent}% GST",          # e.g. '18% GST'       ← most common plain name
                    f"{percent}% GST S",        # e.g. '18% GST S'     ← with suffix
                    f"GST {percent}%",          # e.g. 'GST 18%'
                    f"GST@{percent}%",          # e.g. 'GST@18%'
                    f"{percent}%",              # e.g. '18%'            ← bare percentage
                ]

            _logger.info(
                "Tally tax '%s' → percent=%s, is_igst=%s → trying: %s",
                tax_item, percent, is_igst, candidate_names
            )

        # ── Step 4: Search Odoo for each candidate name (exact match) ─────────
        for odoo_tax_name in candidate_names:
            tax = request.env['account.tax'].sudo().search([
                ('name', '=', odoo_tax_name),
                ('company_id', '=', company.id),
                ('type_tax_use', '=', 'sale')
            ], limit=1)
            if tax:
                _logger.info(
                    "✓ Tally tax '%s' → matched Odoo tax '%s' (id:%s)",
                    tax_item, tax.name, tax.id
                )
                return [tax.id], None

        # ── Step 5: Nothing matched — return clear, actionable error ──────────
        available_taxes = request.env['account.tax'].sudo().search([
            ('company_id', '=', company.id),
            ('type_tax_use', '=', 'sale')
        ]).mapped('name')

        _logger.warning(
            "Tally tax '%s' → tried %s → NO MATCH for company '%s'. Available: %s",
            tax_item, candidate_names, company.name, available_taxes
        )

        return [], {
            'success': False,
            'message': (
                f"Tax '{tax_item}' from Tally could not be matched in Odoo "
                f"for company '{company.name}'. "
                f"Tried: {candidate_names}. "
                f"Available taxes: {available_taxes}"
            ),
            'status': 404
        }


    @http.route('/web/api/create_invoice', type="json", auth="none", methods=['POST'], csrf=False)
    def accountmove_invoice(self, **received_payloads):
        invoice_number = []
        tally_invoice_number = []
        tally_master_id = []
        skipped_invoices = []  # track invoices skipped due to no valid products

        # ── Auto-chunking for large bulk pushes ─────────────────────────────────
        # Tally can send 5,000+ invoices in ONE request. Rather than rejecting
        # it or processing everything in one giant uncommitted transaction
        # (which risks a PostgreSQL/Werkzeug timeout losing the ENTIRE batch),
        # we keep a single flat loop but COMMIT every _CHUNK_SIZE invoices.
        # If something fails at invoice #4,820, invoices #1-4,800 are already
        # safely written to disk — only the remainder needs attention.
        _CHUNK_SIZE = 100
        _incoming_datas = list(received_payloads.get('datas', []))  # mutable copy — can append retries
        _total_incoming = len(_incoming_datas)
        _retry_counts = {}  # id(payload) -> number of concurrent-conflict retries so far
        _MAX_CONCURRENT_RETRIES = 3

        if _total_incoming > _CHUNK_SIZE:
            _logger.info(
                "Bulk push of %d invoices received — will commit progress "
                "every %d invoices for safety.",
                _total_incoming, _CHUNK_SIZE)

        try:
            _processed_count = 0
            _idx = 0
            while _idx < len(_incoming_datas):
                received_payload = _incoming_datas[_idx]
                _idx += 1
                _processed_count += 1

                # Commit progress every _CHUNK_SIZE invoices so a large bulk
                # push never loses everything already processed if something
                # later in the same request fails or the connection is cut.
                if _processed_count % _CHUNK_SIZE == 0:
                    try:
                        request.env.cr.commit()
                        _logger.info(
                            "Bulk push progress: committed after %d/%d invoices "
                            "(created so far: %d, skipped so far: %d)",
                            _processed_count, _total_incoming,
                            len(invoice_number), len(skipped_invoices))
                    except Exception as commit_err:
                        _logger.warning(
                            "Periodic commit failed at invoice #%d: %s",
                            _processed_count, str(commit_err))

                # -------- API Token Validation --------
                api_token = received_payloads.get('api_token')
                if not api_token:
                    return {
                        'success': False,
                        'response': {'origin': received_payload.get('origin')},
                        'message': 'API Token is required',
                        'status': 401
                    }

                company = request.env['res.company'].sudo().search([
                    ('api_token', '=', api_token)
                ], limit=1)

                if not company:
                    return {
                        'success': False,
                        'response': {'origin': received_payload.get('origin')},
                        'message': 'Invalid API Token',
                        'status': 401
                    }

                # -------- Helper: Build Line Commands --------
                def build_line_commands(invoice_line_ids, as_commands=True):
                    """
                    Shared line builder for both create and update flows.
                    as_commands=True  → returns [(0,0,d), ...] for create
                    as_commands=False → returns [(5,0,0), (0,0,d), ...] for update (write)

                    Lines whose product code isn't found are SKIPPED (logged), not
                    treated as a hard failure — Tally bulk pushes often include
                    products that don't belong to every company, and one missing
                    code should never block the rest of a valid invoice.
                    """
                    lines = []
                    skipped = []
                    malformed = []

                    if not isinstance(invoice_line_ids, (list, tuple)):
                        _logger.error(
                            "build_line_commands: invoice_line_ids itself was "
                            "type %s, not a list: %r",
                            type(invoice_line_ids).__name__, invoice_line_ids)
                        return None, {
                            'success': False,
                            'message': (
                                f"invoice_line_ids must be a list of line objects, "
                                f"but received type {type(invoice_line_ids).__name__}. "
                                f"Please check the Tally export format."
                            ),
                            'status': 400
                        }

                    for child_dict in invoice_line_ids:
                        # Tally should send each line as a JSON object. If a
                        # line ever arrives as something else (tuple, list,
                        # string), calling .get() on it crashes with exactly
                        # "'tuple' object has no attribute 'get'". Catch that
                        # here, log/skip it, and keep processing the rest of
                        # the invoice's valid lines instead of failing the
                        # whole update.
                        if not isinstance(child_dict, dict):
                            _logger.error(
                                "build_line_commands: skipping non-dict line "
                                "of type %s: %r", type(child_dict).__name__, child_dict)
                            malformed.append(repr(child_dict))
                            continue

                        # Tally sometimes sends trailing \r\n or stray whitespace on
                        # codes — strip it before searching so a real match isn't
                        # missed just because of invisible characters.
                        raw_code = child_dict.get('default_code') or ''
                        clean_code = raw_code.strip()

                        product = request.env['product.product'].sudo().search([
                            ('default_code', '=', clean_code)
                        ], limit=1)

                        if not product:
                            _logger.warning(
                                "Product with code '%s' not found — skipping this line",
                                clean_code)
                            skipped.append(clean_code or '(blank code)')
                            continue

                        product = product.with_company(company)
                        account = (
                            product.property_account_income_id
                            or product.categ_id.property_account_income_categ_id
                        )

                        if not account:
                            _logger.warning(
                                "No income account configured for product '%s' — skipping this line",
                                product.default_code)
                            skipped.append(product.default_code or clean_code)
                            continue

                        tax_list_ids = child_dict.get('tax_list_ids', [])
                        line_data = {
                            'product_id': product.id,
                            'name': child_dict.get('name') or product.name,
                            'quantity': child_dict.get('quantity', 1),
                            'price_unit': child_dict.get('price_unit', 0.0),
                            'account_id': account.id,
                            'discount': child_dict.get('discount', 0.0),
                            'tally_amount': child_dict.get('tally_amount', 0.0),
                            
                        }

                        if tax_list_ids:
                            if not isinstance(tax_list_ids, list):
                                tax_list_ids = [tax_list_ids]
                            resolved_tax_ids = []
                            for tax_item in tax_list_ids:
                                if isinstance(tax_item, int):
                                    resolved_tax_ids.append(tax_item)
                                elif isinstance(tax_item, str):
                                    ids, error = self._resolve_tally_tax(tax_item, company)
                                    if error:
                                        _logger.warning(
                                            "Tax '%s' not resolved for product '%s' — "
                                            "line kept without this tax",
                                            tax_item, product.default_code)
                                    else:
                                        resolved_tax_ids.extend(ids)
                            line_data['tax_ids'] = [(6, 0, resolved_tax_ids)] if resolved_tax_ids else [(5, 0, 0)]
                        else:
                            line_data['tax_ids'] = [(5, 0, 0)]

                        lines.append(line_data)

                    if skipped:
                        _logger.warning(
                            "build_line_commands: skipped %d line(s) with codes: %s",
                            len(skipped), skipped)

                    if malformed:
                        _logger.error(
                            "build_line_commands: %d line(s) were not valid JSON "
                            "objects and were skipped entirely: %s",
                            len(malformed), malformed)

                    if not lines:
                        # Every single line failed — nothing to update with.
                        # This is still reported as an error since an invoice
                        # with zero lines makes no sense, but it no longer
                        # happens just because ONE line had a bad code.
                        _reason_parts = []
                        if skipped:
                            _reason_parts.append(f"{len(skipped)} product(s) not found: {skipped}")
                        if malformed:
                            _reason_parts.append(
                                f"{len(malformed)} line(s) were malformed (not a JSON "
                                f"object — check Tally export format): {malformed}")
                        return None, {
                            'success': False,
                            'message': (
                                "All lines were skipped — no valid lines to update with. "
                                + " | ".join(_reason_parts)
                            ),
                            'status': 404
                        }

                    if as_commands:
                        return [(0, 0, d) for d in lines], None
                    else:
                        return [(5, 0, 0)] + [(0, 0, d) for d in lines], None

                # -------- Helper: Update Existing Invoice --------
                def update_existing_invoice(existing_invoice, payload):
                    """
                    Updates an existing invoice regardless of its current state.
                    Called both from the duplicate check AND from the constraint catch block.
                    """
                    MAX_RETRIES = 3

                    for attempt in range(1, MAX_RETRIES + 1):

                        try:
                            with request.env.cr.savepoint():

                                inv = (
                                    existing_invoice
                                    .with_company(company)
                                    .with_user(SUPERUSER_ID)
                                )

                                # Lock this invoice row.
                                request.env.cr.execute("""
                                    SELECT id
                                    FROM account_move
                                    WHERE id = %s
                                    FOR UPDATE
                                """, (inv.id,))

                                if inv.state != 'draft':
                                    inv.button_draft()

                                line_commands, error = build_line_commands(
                                    payload.get('invoice_line_ids', []),
                                    as_commands=False
                                )

                                if error:
                                    return error

                                inv.write({
                                    'invoice_origin': payload.get('invoice_origin'),
                                    'invoice_line_ids': line_commands,
                                })

                                inv.action_post()

                                _logger.info(
                                    "Invoice '%s' (id:%s) updated successfully.",
                                    payload.get('tally_invoice_number'),
                                    inv.id
                                )

                                return None

                        except Exception as update_error:

                            error_str = str(update_error)

                            if self._is_concurrency_conflict(error_str):

                                self._safe_rollback(request.env.cr)

                                _logger.warning(
                                    "Concurrent update detected for invoice '%s' "
                                    "(attempt %d/%d). Retrying...",
                                    payload.get('tally_invoice_number'),
                                    attempt,
                                    MAX_RETRIES,
                                )

                                time.sleep(0.5 * attempt)

                                existing_invoice.invalidate_recordset()

                                continue

                            _logger.exception(
                                "Error updating invoice '%s': %s",
                                payload.get('tally_invoice_number'),
                                error_str
                            )

                            self._safe_rollback(request.env.cr)

                            return {
                                'success': False,
                                'message': (
                                    f"Technical error occurred while updating invoice "
                                    f"'{payload.get('tally_invoice_number')}'. "
                                    f"Error: {error_str}"
                                ),
                                'status': 500
                            }

                    return {
                        'success': False,
                        'message': (
                            f"Invoice '{payload.get('tally_invoice_number')}' "
                            f"could not be updated after {MAX_RETRIES} retries "
                            f"because another request kept modifying it."
                        ),
                        'status': 409
                    }

                # -------- Duplicate Check (pre-creation) --------
                duplicate_invoice_obj = request.env['account.move'].sudo().search([
                    ('tally_invoice_number', '=', received_payload.get('tally_invoice_number')),
                    ('company_id', '=', company.id)
                ], limit=1)

                if duplicate_invoice_obj:
                    _logger.info(
                        "Duplicate found for tally_invoice_number='%s' → updating.",
                        received_payload.get('tally_invoice_number')
                    )
                    error = update_existing_invoice(duplicate_invoice_obj, received_payload)
                    if error:
                        return error

                    # ✅ Duplicate updated — track and continue to next invoice
                    invoice_number.append(duplicate_invoice_obj.id)
                    tally_invoice_number.append(received_payload.get('tally_invoice_number'))
                    tally_master_id.append(received_payload.get('tally_master_id'))
                    continue  # ← move to next invoice in bulk

                # -------- New Invoice Creation --------
                try:
                    with request.env.cr.savepoint():
                        sent_company_id = received_payload.get('company_id')
                        sent_primary_key = received_payload.get('company_primary_key')
                        sent_journal_id = received_payload.get('journal_id')

                        mismatch_reasons = []

                        if sent_company_id and int(sent_company_id) != company.id:
                            mismatch_reasons.append(
                                f"company_id {sent_company_id} does not match api_token's "
                                f"company ({company.id} - {company.name})"
                            )

                        if sent_primary_key and company.company_primary_key and \
                                sent_primary_key != company.company_primary_key:
                            mismatch_reasons.append(
                                f"company_primary_key '{sent_primary_key}' does not match "
                                f"api_token's company primary key "
                                f"'{company.company_primary_key}'"
                            )

                        journal = None
                        if sent_journal_id:
                            journal = request.env['account.journal'].sudo().search([
                                ('id', '=', sent_journal_id),
                                ('company_id', '=', company.id),
                            ], limit=1)
                            if not journal:
                                mismatch_reasons.append(
                                    f"journal_id {sent_journal_id} does not belong to "
                                    f"company {company.id} ({company.name})"
                                )

                        if mismatch_reasons:
                            _logger.warning(
                                "Company identity mismatch for invoice '%s' — skipping. "
                                "Reasons: %s",
                                received_payload.get('tally_invoice_number', 'Unknown'),
                                '; '.join(mismatch_reasons)
                            )
                            skipped_invoices.append({
                                'tally_invoice_number': received_payload.get(
                                    'tally_invoice_number', 'Unknown'),
                                'reason': '; '.join(mismatch_reasons),
                            })
                            continue

                        journal_id = journal.id if journal else False
                        received_payload['journal_id'] = journal_id
                        company_primary_key = received_payload.get('company_primary_key')
                        state_id = received_payload.get('state_id')
                        vat = self._clean_gstin(received_payload.get('vat', ''))
                        country_id = received_payload.get('country_id')
                        customer_name = received_payload.get('customer_name')
                        street = received_payload.get('street')
                        street2 = received_payload.get('street2')
                        zipcode = received_payload.get('zip') or received_payload.get('zipcode', '')

                        received_payload['company_id'] = company.id
                        inv_fields = request.env['account.move'].sudo().fields_get()
                        received_payload['is_community_enterprise'] = True

                        mandatory_fields = []
                        received_payload = validations.API.RemoveUnwantedKeys(received_payload)
                        response = validations.API.FieldValidation(inv_fields, received_payload, mandatory_fields)
                        if response:
                            # Don't return here — we're inside a savepoint for THIS invoice
                            # only. Returning abandons the savepoint, corrupts the
                            # transaction, and (in a bulk push) kills every invoice still
                            # queued after this one with "cursor already closed".
                            # Skip just this invoice and let the loop continue instead.
                            _logger.warning(
                                "Header field validation failed for invoice '%s': %s — skipping invoice",
                                received_payload.get('tally_invoice_number', 'Unknown'), response)
                            skipped_invoices.append({
                                'tally_invoice_number': received_payload.get('tally_invoice_number', 'Unknown'),
                                'reason': str(response),
                            })
                            continue

                        processed_main_contact = validations.API.RemoveReferenceFieldNew(received_payload, inv_fields)
                        if not processed_main_contact:
                            _logger.warning(
                                "Source document '%s' not found for invoice '%s' — skipping invoice",
                                received_payload.get('origin'),
                                received_payload.get('tally_invoice_number', 'Unknown'))
                            skipped_invoices.append({
                                'tally_invoice_number': received_payload.get('tally_invoice_number', 'Unknown'),
                                'reason': f"Given source document '{received_payload.get('origin')}' not found!",
                            })
                            continue

                        processed_main_contact['company_id'] = company.id
                        processed_main_contact.update({
                            'state_id': state_id,
                            'street': street,
                            'street2': street2,
                            'zip': zipcode,
                            'vat': self._clean_gstin(vat),
                            'country_id': country_id,
                            'customer_name': customer_name
                        })

                        if received_payload.get('invoice_line_ids'):
                            inv_dict = []
                            skipped_lines = []
                            # Fetch field definitions once outside the loop — same for every line,
                            # no need to query Odoo's ORM metadata 10 times for 10 lines.
                            _aml_fields = request.env['account.move.line'].sudo().fields_get()
                            for child_dict in received_payload.get('invoice_line_ids'):
                                try:
                                    # -------- default_code handling --------
                                    # CASE 1: No default_code → skip this line only, log it
                                    if not child_dict.get('default_code', '').strip():
                                        tally_product_name = child_dict.get('name', 'Unknown')
                                        skipped_lines.append(tally_product_name)
                                        _logger.warning(
                                            "create_invoice: Line skipped — no default_code "
                                            "for product '%s' in tally_invoice_number '%s'",
                                            tally_product_name,
                                            received_payload.get('tally_invoice_number')
                                        )
                                        try:
                                            request.env['tally.sync.log'].sudo().create({
                                                'tally_invoice_number': received_payload.get('tally_invoice_number'),
                                                'tally_master_id': received_payload.get('tally_master_id'),
                                                'company_id': company.id,
                                                'line_product_name': tally_product_name,
                                                'tally_default_code': None,
                                                'odoo_default_code': None,
                                                'missing_code': True,
                                                'status': 'missing',
                                                'notes': "Line SKIPPED: no default_code sent from Tally.",
                                            })
                                        except Exception:
                                            pass  # log model may not exist, don't break invoice
                                        continue  # skip only this line, rest of invoice continues

                                    default_code = child_dict['default_code'].strip()
                                    tally_product_name = child_dict.get('name', 'Unknown')

                                    if 'default_code' in child_dict and child_dict.get('default_code'):
                                        product = request.env['product.product'].sudo().search([
                                            ('default_code', '=', default_code)
                                        ], limit=1)

                                        # CASE 2: Code sent but product NOT found in this company
                                        # → SKIP this line, log it, continue with next line
                                        if not product:
                                            _logger.warning(
                                                "create_invoice: Product code '%s' not found in "
                                                "company '%s' — SKIPPING line for invoice '%s'",
                                                default_code, company.name,
                                                received_payload.get('tally_invoice_number')
                                            )
                                            try:
                                                request.env['tally.sync.log'].sudo().create({
                                                    'tally_invoice_number': received_payload.get('tally_invoice_number'),
                                                    'tally_master_id': received_payload.get('tally_master_id'),
                                                    'company_id': company.id,
                                                    'line_product_name': tally_product_name,
                                                    'tally_default_code': default_code,
                                                    'odoo_default_code': None,
                                                    'missing_code': False,
                                                    'status': 'not_found',
                                                    'notes': f"Line SKIPPED: product '{default_code}' "
                                                             f"not found in company '{company.name}'.",
                                                })
                                            except Exception:
                                                pass
                                            skipped_lines.append(default_code)
                                            continue  # ← skip this line, process next line
                                        else:
                                            # CASE 3: Name mismatch (scheme/fraud detection)
                                            odoo_name = product.name or ''
                                            if tally_product_name.strip().lower() != odoo_name.strip().lower():
                                                _logger.warning(
                                                    "create_invoice: Name mismatch for code '%s': "
                                                    "Tally='%s' vs Odoo='%s' — possible scheme change",
                                                    default_code, tally_product_name, odoo_name
                                                )
                                                try:
                                                    request.env['tally.sync.log'].sudo().create({
                                                        'tally_invoice_number': received_payload.get('tally_invoice_number'),
                                                        'tally_master_id': received_payload.get('tally_master_id'),
                                                        'company_id': company.id,
                                                        'line_product_name': tally_product_name,
                                                        'tally_default_code': default_code,
                                                        'odoo_default_code': product.default_code,
                                                        'mismatch': True,
                                                        'status': 'mismatch',
                                                        'notes': f"Name mismatch: Tally='{tally_product_name}', "
                                                                 f"Odoo='{odoo_name}' for code '{default_code}'. "
                                                                 f"Possible scheme benefit change. Line included.",
                                                    })
                                                except Exception:
                                                    pass
                                            else:
                                                # CASE 4: Perfect match
                                                try:
                                                    request.env['tally.sync.log'].sudo().create({
                                                        'tally_invoice_number': received_payload.get('tally_invoice_number'),
                                                        'tally_master_id': received_payload.get('tally_master_id'),
                                                        'company_id': company.id,
                                                        'line_product_name': tally_product_name,
                                                        'tally_default_code': default_code,
                                                        'odoo_default_code': product.default_code,
                                                        'status': 'ok',
                                                        'notes': 'Product matched successfully.',
                                                    })
                                                except Exception:
                                                    pass

                                            # Set product_id only when product is found
                                            child_dict['product_id'] = product.id
                                    # -------- end default_code handling --------

                                    tax_list_ids = child_dict.get('tax_list_ids', [])
                                    child_dict['is_community_enterprise'] = True
                                    child_dict['company_id'] = company.id

                                    purchase_line_fields = _aml_fields  # cached outside the loop
                                    processed_dict = validations.API.RemoveUnwantedKeys(child_dict)
                                    # FieldValidation is bypassed here — it is too strict for invoice
                                    # lines (rejects int where float is expected, rejects monetary
                                    # fields outright) and Odoo's ORM already coerces types safely on
                                    # create(). A `return` from here also used to abandon the open
                                    # savepoint, which is what was corrupting the DB transaction and
                                    # causing "cursor already closed" on every subsequent line/tax query.
                                    response = False

                                    processed_dict_delivery = validations.API.RemoveReferenceFieldNew(processed_dict, purchase_line_fields)
                                    processed_dict_delivery['company_id'] = company.id
                                    processed_dict_delivery['discount'] = child_dict.get('discount', 0.0)
                                    processed_dict_delivery['tally_amount'] = child_dict.get('tally_amount', 0.0)

                                    if tax_list_ids:
                                        if not isinstance(tax_list_ids, list):
                                            tax_list_ids = [tax_list_ids]
                                        resolved_tax_ids = []
                                        for tax_item in tax_list_ids:
                                            if isinstance(tax_item, int):
                                                resolved_tax_ids.append(tax_item)
                                            elif isinstance(tax_item, str):
                                                ids, error = self._resolve_tally_tax(tax_item, company)
                                                if error:
                                                    # Log tax error but don't abort — skip tax, continue with no tax
                                                    _logger.warning(
                                                        "Tax '%s' not resolved for product '%s' "
                                                        "in invoice '%s' — line added without tax.",
                                                        tax_item,
                                                        child_dict.get('default_code', 'Unknown'),
                                                        received_payload.get('tally_invoice_number')
                                                    )
                                                else:
                                                    resolved_tax_ids.extend(ids)
                                        processed_dict_delivery['tax_ids'] = [(6, 0, resolved_tax_ids)] if resolved_tax_ids else [(5, 0, 0)]
                                    else:
                                        processed_dict_delivery['tax_ids'] = [(5, 0, 0)]

                                    inv_dict.append(processed_dict_delivery)

                                except Exception as line_error:
                                    _logger.warning(
                                        "Line error for product '%s' in invoice '%s' — "
                                        "SKIPPING this line: %s",
                                        child_dict.get('default_code'), 
                                        received_payload.get('tally_invoice_number'),
                                        str(line_error))
                                    skipped_lines.append(child_dict.get('default_code', 'Unknown'))
                                    continue  # ← skip this line, continue with next line
                            # If ALL lines were skipped — skip this invoice, continue to next
                            if not inv_dict:
                                _logger.warning(
                                    "Invoice '%s' SKIPPED — all lines had no valid product "
                                    "in this company. Skipped: %s",
                                    received_payload.get('tally_invoice_number'), skipped_lines
                                )
                                skipped_invoices.append({
                                    'tally_invoice_number': received_payload.get('tally_invoice_number'),
                                    'reason': f"All lines skipped — no valid product found. Skipped: {skipped_lines}"
                                })
                                continue  # ← skip this invoice, process remaining
        

                            for line_dict in inv_dict:
                                line_dict['company_id'] = company.id

                            processed_main_contact['invoice_line_ids'] = [(0, 0, d) for d in inv_dict]

                        env = request.env(user=company.user_ids[0].id if company.user_ids else 1)
                        partner_obj = env['account.move'].sudo().with_company(company).create(processed_main_contact)
                        partner_obj.write({'company_primary_key': company_primary_key})
                        partner_obj.sudo().action_post()

                        # ── Auto-create outgoing delivery for stock update ──
                        # Customer invoice alone never updates stock in Odoo.
                        # We must create a stock.picking (delivery) and validate
                        # it so quantities appear in stock valuation layer.
                        try:
                            delivery = self._create_and_validate_delivery(
                                partner_obj, company)
                            if isinstance(delivery, dict):
                                _logger.warning(
                                    "Invoice '%s' created but delivery failed: %s",
                                    received_payload.get('tally_invoice_number'),
                                    delivery.get('message'))
                            elif delivery:
                                _logger.info(
                                    "✓ Delivery '%s' validated for invoice '%s'",
                                    delivery.name,
                                    received_payload.get('tally_invoice_number'))
                        except Exception as de:
                            _logger.warning(
                                "Delivery creation failed for invoice '%s' (non-fatal): %s",
                                received_payload.get('tally_invoice_number'), str(de))

                        # Back-fill invoice_id on logs written above for this invoice
                        request.env['tally.sync.log'].sudo().search([
                            ('tally_invoice_number', '=', received_payload.get('tally_invoice_number')),
                            ('invoice_id', '=', False),
                        ]).write({'invoice_id': partner_obj.id})

                        invoice_number.append(partner_obj.id)
                        tally_invoice_number.append(received_payload.get('tally_invoice_number'))
                        tally_master_id.append(received_payload.get('tally_master_id'))

                except Exception as create_error:
                    error_str = str(create_error)


                    # This happens in race conditions or when duplicate check is bypassed
                    if 'account_move_unique_tally_invoice_company' in error_str or \
                    'duplicate key value violates unique constraint' in error_str:

                        _logger.warning(
                            "Duplicate constraint hit during creation for '%s' → switching to update flow.",
                            received_payload.get('tally_invoice_number')
                        )

                        # Rollback first
                        self._safe_rollback(request.env.cr)

                        # Give PostgreSQL a moment to finish the other transaction
                        time.sleep(0.5)

                        existing = False

                        # Retry searching a few times because another request may still be committing
                        for attempt in range(5):
                            existing = request.env['account.move'].sudo().search([
                                ('tally_invoice_number', '=', received_payload.get('tally_invoice_number')),
                                ('company_id', '=', company.id)
                            ], limit=1)

                            if existing:
                                break

                            time.sleep(0.3)

                        if existing:

                            # Lock the row before updating
                            request.env.cr.execute("""
                                SELECT id
                                FROM account_move
                                WHERE id=%s
                                FOR UPDATE
                            """, (existing.id,))

                            error = update_existing_invoice(existing, received_payload)

                            if error:
                                return error

                            invoice_number.append(existing.id)
                            tally_invoice_number.append(received_payload.get('tally_invoice_number'))
                            tally_master_id.append(received_payload.get('tally_master_id'))
                            continue

                        else:
                            _logger.error(
                                "Duplicate invoice '%s' exists but was not found after retries.",
                                received_payload.get('tally_invoice_number')
                            )

                            return {
                                'success': False,
                                'message': (
                                    f"Duplicate invoice '{received_payload.get('tally_invoice_number')}' "
                                    f"could not be found after retrying."
                                ),
                                'status': 409
                            }

                    else:
                        # Concurrent-update conflict — e.g. Tally fired the same
                        # brand-new voucher twice almost simultaneously. Requeue
                        # this exact payload to be retried later in the SAME
                        # pass (appended to the end of the list we're iterating)
                        # instead of skipping immediately — by the time we reach
                        # it again, the other request touching this row will
                        # almost certainly have committed.
                        if self._is_concurrency_conflict(error_str):
                            self._safe_rollback(request.env.cr)
                            _payload_key = id(received_payload)
                            _retries_so_far = _retry_counts.get(_payload_key, 0)
                            if _retries_so_far < _MAX_CONCURRENT_RETRIES:
                                _retry_counts[_payload_key] = _retries_so_far + 1
                                _logger.warning(
                                    "Concurrent update conflict creating invoice '%s' "
                                    "(retry %d/%d) — requeued for another attempt.",
                                    received_payload.get('tally_invoice_number', 'Unknown'),
                                    _retries_so_far + 1, _MAX_CONCURRENT_RETRIES)
                                time.sleep(0.3)  # brief pause before it's retried later in this pass
                                _incoming_datas.append(received_payload)
                            else:
                                _logger.error(
                                    "Invoice '%s' failed %d times due to concurrent "
                                    "update conflicts — giving up.",
                                    received_payload.get('tally_invoice_number', 'Unknown'),
                                    _MAX_CONCURRENT_RETRIES)
                                skipped_invoices.append({
                                    'tally_invoice_number': received_payload.get('tally_invoice_number', 'Unknown'),
                                    'reason': f"Failed after {_MAX_CONCURRENT_RETRIES} retries: {error_str}",
                                })
                            continue

                        # Genuine creation error — not a duplicate issue.
                        # Skip this one invoice and continue with the rest of the
                        # bulk batch instead of aborting everything Tally sent.
                        _logger.exception(
                            "Technical error while creating invoice '%s': %s",
                            received_payload.get('tally_invoice_number', 'Unknown'),
                            error_str)
                        self._safe_rollback(request.env.cr)
                        skipped_invoices.append({
                            'tally_invoice_number': received_payload.get('tally_invoice_number', 'Unknown'),
                            'reason': error_str,
                        })
                        continue

        # -------- Catch-all --------
        except Exception as e:
            _logger.exception("Unexpected error in create_invoice API: %s", str(e))
            self._safe_rollback(request.env.cr)
            return {
                'success': False,
                'message': (
                    f"An unexpected technical error occurred. "
                    f"Please contact your Odoo administrator. "
                    f"Error: {str(e)}"
                ),
                'status': 500
            }

        return {
            'success': True,
            'response': {'Invoice_Created': invoice_number},
            'message': 'Success' if not skipped_invoices else (
                f"Partial success: {len(invoice_number)} invoice(s) created, "
                f"{len(skipped_invoices)} skipped (products not found in this company)."
            ),
            'status': 200,
            'Tally invoice number': tally_invoice_number,
            'Tally Master Id': tally_master_id,
            'Skipped_Invoices': skipped_invoices,  # list of {tally_invoice_number, reason}
        }


    @http.route('/web/api/cancel_invoice', type='json', auth='none', methods=['POST'], csrf=False)
    def accountmove_invoice_cancel(self, **kw):
        """
        Public entrypoint — retries automatically on a concurrent-update
        conflict, same pattern as accountmove_invoice_update. See that
        function's docstring for the full explanation.
        """
        _MAX_RETRIES = 3
        _last_error = None

        for _attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self._do_cancel_invoice(**kw)
            except Exception as e:
                error_str = str(e)
                _last_error = error_str
                if self._is_concurrency_conflict(error_str):
                    self._safe_rollback(request.env.cr)
                    _logger.warning(
                        "Concurrent update conflict cancelling invoice '%s' "
                        "(attempt %d/%d) — retrying shortly.",
                        kw.get('tally_invoice_number', 'Unknown'), _attempt, _MAX_RETRIES)
                    time.sleep(0.5 * _attempt)
                    continue
                raise

        _logger.error(
            "Invoice '%s' cancellation failed after %d retries due to repeated "
            "concurrent update conflicts. Last error: %s",
            kw.get('tally_invoice_number', 'Unknown'), _MAX_RETRIES, _last_error)
        return {
            'success': False,
            'status': 409,
            'response': (
                f"Invoice '{kw.get('tally_invoice_number', 'Unknown')}' could not be "
                f"cancelled after {_MAX_RETRIES} attempts due to a concurrent update "
                f"conflict. Please retry this cancellation again."
            )
        }

    def _do_cancel_invoice(self, **kw):
        try:
            # -------- Required Fields Check --------
            required_fields = ['tally_invoice_number', 'vch_primary_key', 'api_token', 'invoice_origin', 'company_primary_key']
            missing_fields = [f for f in required_fields if not kw.get(f)]
            if missing_fields:
                return {
                    'success': False,
                    'status': 400,
                    'response': f"Missing required fields: {', '.join(missing_fields)}"
                }

            # -------- Search Invoice --------
            try:
                invoice = request.env['account.move'].sudo().search([
                    ('tally_invoice_number', '=', kw.get('tally_invoice_number')),
                    ('vch_primary_key', '=', kw.get('vch_primary_key')),
                ], limit=1)

                # Explicit row lock — if another request is already working on
                # this exact invoice, fail immediately and cleanly instead of
                # racing both transactions to the finish line and letting
                # PostgreSQL pick a winner later with a less predictable
                # "could not serialize access" error. NOWAIT means this
                # raises right away rather than blocking and waiting.
                if invoice:
                    request.env.cr.execute(
                        "SELECT id FROM account_move WHERE id = %s FOR UPDATE NOWAIT",
                        (invoice.id,)
                    )
            except Exception as search_error:
                _logger.exception("Technical error while searching invoice: %s", str(search_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Technical error occurred while searching for invoice "
                        f"'{kw.get('tally_invoice_number')}'. "
                        f"Please contact your Odoo administrator. "
                        f"Error: {str(search_error)}"
                    )
                }

            if not invoice:
                return {
                    'success': False,
                    'status': 404,
                    'response': f"Invoice '{kw.get('tally_invoice_number')}' with the given vch_primary_key does not exist in Odoo."
                }

            # -------- Security Checks --------
            if invoice.company_id.api_token != kw.get('api_token'):
                return {
                    'success': False,
                    'status': 401,
                    'response': 'API token does not match. Please verify your credentials.'
                }

            if invoice.invoice_origin != kw.get('invoice_origin'):
                return {
                    'success': False,
                    'status': 400,
                    'response': f"invoice_origin mismatch. Expected '{invoice.invoice_origin}', received '{kw.get('invoice_origin')}'."
                }

            if invoice.company_primary_key != kw.get('company_primary_key'):
                return {
                    'success': False,
                    'status': 400,
                    'response': f"company_primary_key mismatch. Please verify the company details."
                }

            # -------- State Check --------
            if invoice.state == 'cancel':
                return {
                    'success': False,
                    'status': 409,
                    'response': f"Invoice '{invoice.name}' is already cancelled."
                }

            if invoice.state == 'draft':
                return {
                    'success': False,
                    'status': 409,
                    'response': f"Invoice '{invoice.name}' is in draft state and cannot be cancelled directly."
                }

            # -------- Cancel Invoice --------
            try:
                company = invoice.company_id
                invoice = (
                    invoice
                    .with_company(company)
                    .with_user(SUPERUSER_ID)
                )
                invoice.button_cancel()

            except Exception as cancel_error:
                self._reraise_if_concurrent_conflict(str(cancel_error))
                _logger.exception("Technical error while cancelling invoice: %s", str(cancel_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Technical error occurred while cancelling invoice '{kw.get('tally_invoice_number')}'. "
                        f"Please contact your Odoo administrator. "
                        f"Error: {str(cancel_error)}"
                    )
                }

            return {
                'success': True,
                'status': 200,
                'message': 'Success',
                'response': f"Invoice '{invoice.name}' cancelled successfully.",
                'invoice_number': invoice.name
            }

        # -------- Catch-all for unexpected errors --------
        except Exception as e:
            error_str = str(e)
            if self._is_concurrency_conflict(error_str):
                self._safe_rollback(request.env.cr)
                raise
            _logger.exception("Unexpected technical error in cancel_invoice API: %s", str(e))
            return {
                'success': False,
                'status': 500,
                'response': (
                    f"An unexpected technical error occurred while processing cancellation "
                    f"for invoice '{kw.get('tally_invoice_number', 'Unknown')}'. "
                    f"Please contact your Odoo administrator immediately. "
                    f"Error: {str(e)}"
                )
            }

    

    @http.route('/web/api/update_invoice', type='json', auth='none', methods=['POST'], csrf=False)
    def accountmove_invoice_update(self, **kw):
        """
        Public entrypoint — retries automatically if two requests for the
        SAME invoice arrive close together and PostgreSQL rejects one with
        "could not serialize access due to concurrent update". This is not
        a bug in the query; it's PostgreSQL protecting against a genuine
        race (e.g. Tally resending an invoice before the first attempt's
        transaction has finished committing). Retrying after the first
        attempt's transaction has settled almost always succeeds cleanly.
        """
        _MAX_RETRIES = 3
        _last_error = None

        for _attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self._do_update_invoice(**kw)
            except Exception as e:
                error_str = str(e)
                _last_error = error_str
                if self._is_concurrency_conflict(error_str):
                    self._safe_rollback(request.env.cr)
                    _logger.warning(
                        "Concurrent update conflict on invoice '%s' "
                        "(attempt %d/%d) — retrying shortly.",
                        kw.get('tally_invoice_number', 'Unknown'), _attempt, _MAX_RETRIES)
                    time.sleep(0.5 * _attempt)  # brief backoff before retrying
                    continue
                # Any other error — don't retry, fail immediately as before
                raise

        # All retries exhausted
        _logger.error(
            "Invoice '%s' update failed after %d retries due to repeated "
            "concurrent update conflicts. Last error: %s",
            kw.get('tally_invoice_number', 'Unknown'), _MAX_RETRIES, _last_error)
        return {
            'success': False,
            'status': 409,
            'response': (
                f"Invoice '{kw.get('tally_invoice_number', 'Unknown')}' could not be "
                f"updated after {_MAX_RETRIES} attempts due to a concurrent update "
                f"conflict — another request was modifying the same invoice at the "
                f"same time. Please retry this invoice again."
            )
        }

    def _do_update_invoice(self, **kw):
        try:
            _logger.info('Update invoice payload: %s', kw)

            # -------- Required Fields Check --------
            required_fields = ['tally_invoice_number', 'vch_primary_key', 'api_token', 'company_primary_key']
            missing_fields = [f for f in required_fields if not kw.get(f)]
            if missing_fields:
                return {
                    'success': False,
                    'status': 400,
                    'response': f"Missing required fields: {', '.join(missing_fields)}"
                }

            # -------------------------
            # 1. Fetch Invoice
            # -------------------------
            try:
                invoice = request.env['account.move'].sudo().search([
                    ('tally_invoice_number', '=', kw.get('tally_invoice_number')),
                    ('vch_primary_key', '=', kw.get('vch_primary_key')),
                ], limit=1)

                # Explicit row lock — same reasoning as in cancel_invoice above.
                # Fail fast and predictably if another request is already
                # updating this exact invoice, rather than letting both race.
                if invoice:
                    request.env.cr.execute(
                        "SELECT id FROM account_move WHERE id = %s FOR UPDATE NOWAIT",
                        (invoice.id,)
                    )
            except Exception as search_error:
                _logger.exception("Technical error while searching invoice: %s", str(search_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Technical error occurred while searching for invoice "
                        f"'{kw.get('tally_invoice_number')}'. "
                        f"Please contact your Odoo administrator. "
                        f"Error: {str(search_error)}"
                    )
                }

            if not invoice:
                return {
                    'success': False,
                    'status': 404,
                    'response': f"Invoice '{kw.get('tally_invoice_number')}' with the given vch_primary_key does not exist in Odoo."
                }

            # -------------------------
            # 2. Security Checks
            # -------------------------
            if invoice.company_id.api_token != kw.get('api_token'):
                return {
                    'success': False,
                    'status': 401,
                    'response': 'API token does not match. Please verify your credentials.'
                }

            if invoice.company_primary_key != kw.get('company_primary_key'):
                return {
                    'success': False,
                    'status': 400,
                    'response': 'company_primary_key mismatch. Please verify the company details.'
                }

            # -------- State Check --------
            if invoice.state == 'cancel':
                return {
                    'success': False,
                    'status': 409,
                    'response': f"Invoice '{invoice.name}' is cancelled and cannot be updated."
                }

            company = invoice.company_id

            # -------------------------
            # 3. Safe Environment
            # -------------------------
            try:
                safe_env = request.env(
                    user=SUPERUSER_ID,
                    context={
                        **request.env.context,
                        'allowed_company_ids': [company.id],
                        'force_company': company.id,
                        'mail_notrack': True,
                        'tracking_disable': True,
                    }
                )
                invoice = safe_env['account.move'].browse(invoice.id).with_company(company)
            except Exception as env_error:
                _logger.exception("Technical error while setting up environment: %s", str(env_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Technical error occurred while preparing environment for invoice "
                        f"'{kw.get('tally_invoice_number')}'. "
                        f"Please contact your Odoo administrator. "
                        f"Error: {str(env_error)}"
                    )
                }

            # -------------------------
            # 4. Move to Draft
            # -------------------------
            try:
                if invoice.state == 'posted':
                    invoice.button_draft()
            except Exception as draft_error:
                self._reraise_if_concurrent_conflict(str(draft_error))
                _logger.exception("Technical error while resetting invoice to draft: %s", str(draft_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Technical error occurred while resetting invoice "
                        f"'{invoice.name}' to draft. "
                        f"Please contact your Odoo administrator. "
                        f"Error: {str(draft_error)}"
                    )
                }

            # -------------------------
            # 5. Remove Old Lines
            # -------------------------
            try:
                invoice.invoice_line_ids.unlink()
            except Exception as unlink_error:
                self._reraise_if_concurrent_conflict(str(unlink_error))
                _logger.exception("Technical error while removing invoice lines: %s", str(unlink_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Technical error occurred while clearing existing lines "
                        f"for invoice '{invoice.name}'. "
                        f"Please contact your Odoo administrator. "
                        f"Error: {str(unlink_error)}"
                    )
                }

            # -------------------------
            # 6. Build New Lines
            # -------------------------
            new_lines = []

            for line in kw.get('invoice_line_ids', []):
                try:
                    # Tally should send each line as a JSON object (Python
                    # dict). If a line ever arrives as something else — a
                    # tuple, a string, a list — calling .get() on it is what
                    # produces "'tuple' object has no attribute 'get'".
                    # Catch that here with a clear message naming the
                    # actual line content, instead of crashing deeper in.
                    if not isinstance(line, dict):
                        _logger.error(
                            "Invoice '%s' update: invoice_line_ids contained "
                            "a non-dict line of type %s: %r",
                            kw.get('tally_invoice_number', 'Unknown'),
                            type(line).__name__, line)
                        return {
                            'success': False,
                            'status': 400,
                            'response': (
                                f"One of the lines in 'invoice_line_ids' for invoice "
                                f"'{kw.get('tally_invoice_number', 'Unknown')}' was sent as "
                                f"a {type(line).__name__} instead of a JSON object. "
                                f"Please check the Tally-side payload formatting — each "
                                f"entry in invoice_line_ids must be an object with keys "
                                f"like default_code, quantity, price_unit, etc. "
                                f"Received: {line!r}"
                            )
                        }

                    product = safe_env['product.product'].search([
                        ('default_code', '=', (line.get('default_code') or '').strip())
                    ], limit=1)

                    if not product:
                        return {
                            'success': False,
                            'status': 404,
                            'message': f"Product with code '{line.get('default_code')}' and name '{line.get('name')}' not found",
                        }

                    product = product.with_company(company)

                    if invoice.move_type in ('out_invoice', 'out_refund'):
                        account = (
                            product.property_account_income_id
                            or product.categ_id.property_account_income_categ_id
                        )
                    else:
                        account = (
                            product.property_account_expense_id
                            or product.categ_id.property_account_expense_categ_id
                        )

                    if not account:
                        return {
                            'success': False,
                            'status': 400,
                            'response': (
                                f"No account configured for product '{product.default_code}'. "
                                f"Please configure the income/expense account in Odoo."
                            )
                        }

                    # ── Tax resolution ──────────────────────────────────────
                    # Support BOTH payload shapes:
                    #   tax_ids       → already-resolved Odoo integer tax IDs
                    #   tax_list_ids  → Tally tax NAMES (e.g. "18% GST"), same
                    #                   format used by every other endpoint
                    #                   in this module (create_invoice, vendor
                    #                   bills, etc.) — resolved the same way.
                    raw_tax_ids = line.get('tax_ids', [])
                    tax_list_ids = line.get('tax_list_ids', [])

                    resolved_tax_ids = []

                    if raw_tax_ids:
                        # Already integer IDs — guard against any unexpected
                        # shape (e.g. a list containing a tuple/dict by
                        # mistake) rather than passing it straight into an
                        # ORM domain.
                        for t in raw_tax_ids:
                            if isinstance(t, int):
                                resolved_tax_ids.append(t)
                            else:
                                _logger.warning(
                                    "Ignoring unexpected tax_ids entry of type "
                                    "%s for product '%s': %r",
                                    type(t).__name__, product.default_code, t)

                    if tax_list_ids:
                        if not isinstance(tax_list_ids, list):
                            tax_list_ids = [tax_list_ids]
                        for tax_item in tax_list_ids:
                            if isinstance(tax_item, int):
                                resolved_tax_ids.append(tax_item)
                            elif isinstance(tax_item, str):
                                ids, err = self._resolve_tally_tax(tax_item, company)
                                if err:
                                    _logger.warning(
                                        "Tax '%s' not resolved for product '%s' in "
                                        "invoice '%s' — line kept without this tax.",
                                        tax_item, product.default_code, invoice.name)
                                else:
                                    resolved_tax_ids.extend(ids)
                            else:
                                _logger.warning(
                                    "Ignoring unexpected tax_list_ids entry of type "
                                    "%s for product '%s': %r",
                                    type(tax_item).__name__, product.default_code, tax_item)

                    if raw_tax_ids and not resolved_tax_ids and not tax_list_ids:
                        # Caller explicitly sent tax_ids but every one of them
                        # was an unusable shape, AND no tax_list_ids fallback
                        # was given either — surface this clearly rather than
                        # silently posting the line with zero tax.
                        return {
                            'success': False,
                            'status': 404,
                            'response': (
                                f"One or more tax IDs {raw_tax_ids} could not be used "
                                f"for company '{company.name}'. "
                                f"Please verify tax configuration in Odoo, or send "
                                f"'tax_list_ids' with Tally tax names instead."
                            )
                        }

                    tax_cmd = [(6, 0, resolved_tax_ids)] if resolved_tax_ids else [(5, 0, 0)]

                    new_lines.append((0, 0, {
                        'product_id': product.id,
                        'name': line.get('name') or product.name,
                        'quantity': line.get('quantity', 1),
                        'price_unit': line.get('price_unit', 0.0),
                        'account_id': account.id,
                        'tax_ids': tax_cmd,
                    }))

                except Exception as line_error:
                    _logger.exception("Technical error processing invoice line: %s", str(line_error))
                    return {
                        'success': False,
                        'status': 500,
                        'response': (
                            f"Technical error while processing invoice line "
                            f"for product '{line.get('default_code', 'Unknown') if isinstance(line, dict) else repr(line)}'. "
                            f"Please contact your Odoo administrator. "
                            f"Error: {str(line_error)}"
                        )
                    }

            # -------------------------
            # 7. Write Invoice
            # -------------------------
            try:
                invoice.write({
                    'invoice_origin': kw.get('invoice_origin'),
                    'invoice_line_ids': new_lines,
                })
            except Exception as write_error:
                self._reraise_if_concurrent_conflict(str(write_error))
                _logger.exception("Technical error while writing invoice: %s", str(write_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Technical error occurred while saving updated data "
                        f"for invoice '{invoice.name}'. "
                        f"Please contact your Odoo administrator. "
                        f"Error: {str(write_error)}"
                    )
                }

            # -------------------------
            # 8. Re-Post Invoice
            # -------------------------
            try:
                invoice.action_post()
            except Exception as post_error:
                self._reraise_if_concurrent_conflict(str(post_error))
                _logger.exception("Technical error while re-posting invoice: %s", str(post_error))
                return {
                    'success': False,
                    'status': 500,
                    'response': (
                        f"Invoice '{invoice.name}' was updated but could not be re-posted. "
                        f"Please re-post it manually in Odoo. "
                        f"Error: {str(post_error)}"
                    )
                }

            return {
                'success': True,
                'status': 200,
                'message': 'Invoice updated successfully',
                'invoice_number': invoice.name,
            }

        # -------- Catch-all for unexpected errors --------
        except Exception as e:
            error_str = str(e)
            # Let concurrent-update conflicts bubble up to the outer retry
            # wrapper (accountmove_invoice_update) instead of swallowing
            # them here — those are worth automatically retrying.
            if self._is_concurrency_conflict(error_str):
                self._safe_rollback(request.env.cr)
                raise
            _logger.exception("Unexpected technical error in update_invoice API: %s", str(e))
            return {
                'success': False,
                'status': 500,
                'response': (
                    f"An unexpected technical error occurred while updating invoice "
                    f"'{kw.get('tally_invoice_number', 'Unknown')}'. "
                    f"Please contact your Odoo administrator immediately. "
                    f"Error: {str(e)}"
                )
            }

    @http.route('/web/api/create_credit_note', type='json', auth='none', methods=['POST'], csrf=False)
    def create_credit_note(self, **received_payloads):
        credit_note_numbers = []
        tally_credit_note_numbers = []
        tally_master_ids = []
        skipped_credit_notes = []
        _retry_counts = {}
        _MAX_CONCURRENT_RETRIES = 3
        _incoming_cn_datas = list(received_payloads.get('datas', []))  # mutable — allows requeue on conflict

        try:
            _idx = 0
            while _idx < len(_incoming_cn_datas):
                received_payload = _incoming_cn_datas[_idx]
                _idx += 1

                # -------- Required Fields Check --------
                required_fields = ['tally_credit_note_number', 'tally_master_id']
                missing_fields = [f for f in required_fields if not received_payload.get(f)]
                if missing_fields:
                    return {
                        'success': False,
                        'status': 400,
                        'message': f"Missing required fields: {', '.join(missing_fields)}"
                    }

                if not received_payload.get('original_invoice_number') and not received_payload.get('tally_invoice_number'):
                    return {
                        'success': False,
                        'status': 400,
                        'message': "Either 'original_invoice_number' or 'tally_invoice_number' is required."
                    }

                # -------- 1. Authenticate --------
                api_token = received_payloads.get('api_token')
                if not api_token:
                    return {
                        'success': False,
                        'status': 401,
                        'message': 'API Token is required.'
                    }

                try:
                    company = request.env['res.company'].sudo().search([
                        ('api_token', '=', api_token)
                    ], limit=1)
                except Exception as auth_error:
                    _logger.exception("Technical error during authentication: %s", str(auth_error))
                    return {
                        'success': False,
                        'status': 500,
                        'message': (
                            f"Technical error occurred during authentication. "
                            f"Please contact your Odoo administrator. "
                            f"Error: {str(auth_error)}"
                        )
                    }

                if not company:
                    return {
                        'success': False,
                        'status': 401,
                        'message': 'Invalid API Token.'
                    }

                # -------- 2. Duplicate Check --------
                try:
                    duplicate_credit_note = request.env['account.move'].sudo().search([
                        ('tally_invoice_number', '=', received_payload.get('tally_credit_note_number')),
                        ('company_id', '=', company.id),
                        ('move_type', '=', 'out_refund')
                    ], limit=1)
                except Exception as dup_error:
                    _logger.exception("Technical error during duplicate check: %s", str(dup_error))
                    return {
                        'success': False,
                        'status': 500,
                        'message': (
                            f"Technical error occurred while checking for duplicate credit note "
                            f"'{received_payload.get('tally_credit_note_number')}'. "
                            f"Please contact your Odoo administrator. "
                            f"Error: {str(dup_error)}"
                        )
                    }

                if duplicate_credit_note:
                    return {
                        'success': False,
                        'status': 409,
                        'message': (
                            f"Credit note '{received_payload.get('tally_credit_note_number')}' "
                            f"already exists in Odoo as '{duplicate_credit_note.name}'."
                        ),
                        'existing_credit_note': duplicate_credit_note.name
                    }

                # -------- 3. Find Original Invoice --------
                try:
                    original_invoice = None

                    if received_payload.get('original_invoice_number'):
                        original_invoice = request.env['account.move'].sudo().search([
                            ('name', '=', received_payload.get('original_invoice_number')),
                            ('company_id', '=', company.id),
                            ('move_type', '=', 'out_invoice'),
                            ('state', '=', 'posted')
                        ], limit=1)

                    if not original_invoice and received_payload.get('tally_invoice_number'):
                        original_invoice = request.env['account.move'].sudo().search([
                            ('tally_invoice_number', '=', received_payload.get('tally_invoice_number')),
                            ('company_id', '=', company.id),
                            ('move_type', '=', 'out_invoice'),
                            ('state', '=', 'posted')
                        ], limit=1)

                except Exception as inv_search_error:
                    _logger.exception("Technical error while searching original invoice: %s", str(inv_search_error))
                    return {
                        'success': False,
                        'status': 500,
                        'message': (
                            f"Technical error occurred while searching for the original invoice. "
                            f"Please contact your Odoo administrator. "
                            f"Error: {str(inv_search_error)}"
                        )
                    }

                if not original_invoice:
                    return {
                        'success': False,
                        'status': 404,
                        'message': (
                            f"Original invoice not found or not in posted state. "
                            f"Searched by: "
                            f"Odoo number='{received_payload.get('original_invoice_number')}', "
                            f"Tally number='{received_payload.get('tally_invoice_number')}'."
                        )
                    }

                # -------- 4. Prepare Credit Note Data --------
                credit_note_data = {
                    'move_type': 'out_refund',
                    'partner_id': original_invoice.partner_id.id,
                    'company_id': company.id,
                    'currency_id': original_invoice.currency_id.id,
                    'invoice_date': received_payload.get('credit_note_date') or fields.Date.today(),
                    'invoice_origin': original_invoice.name,
                    'ref': received_payload.get('reason', 'Credit Note'),
                    'tally_invoice_number': received_payload.get('tally_credit_note_number'),
                    'tally_master_id': received_payload.get('tally_master_id'),
                    'company_primary_key': received_payload.get('company_primary_key', ''),
                    'reversed_entry_id': original_invoice.id,
                }

                # -------- 5. Build Invoice Lines --------
                invoice_lines = []

                for line_data in received_payload.get('invoice_line_ids', []):
                    try:
                        product = request.env['product.product'].sudo().search([
                            ('default_code', '=', (line_data.get('default_code') or '').strip())
                        ], limit=1)

                        if not product:
                            return {
                                'success': False,
                                'status': 404,
                                'message': f"Product with code '{child_dict.get('default_code')}' and name '{child_dict.get('name')}' not found",
                            }

                        product = product.with_company(company)

                        account = (
                            product.property_account_income_id
                            or product.categ_id.property_account_income_categ_id
                        )

                        if not account:
                            return {
                                'success': False,
                                'status': 400,
                                'message': (
                                    f"No income account configured for product '{product.default_code}'. "
                                    f"Please configure it in Odoo."
                                )
                            }

                        tax_ids = []
                        if line_data.get('tax_list_ids'):
                            try:
                                tax_names = line_data.get('tax_list_ids').split(',')
                                for tax_name in tax_names:
                                    tax = request.env['account.tax'].sudo().search([
                                        ('name', '=', tax_name.strip()),
                                        ('company_id', '=', company.id),
                                        ('type_tax_use', '=', 'sale')
                                    ], limit=1)
                                    if not tax:
                                        return {
                                            'success': False,
                                            'status': 404,
                                            'message': (
                                                f"Tax '{tax_name.strip()}' not found for company '{company.name}'. "
                                                f"Please configure it in Odoo."
                                            )
                                        }
                                    tax_ids.append(tax.id)
                            except Exception as tax_error:
                                _logger.exception("Technical error processing taxes: %s", str(tax_error))
                                return {
                                    'success': False,
                                    'status': 500,
                                    'message': (
                                        f"Technical error while processing taxes for product '{product.default_code}'. "
                                        f"Please contact your Odoo administrator. "
                                        f"Error: {str(tax_error)}"
                                    )
                                }

                        invoice_lines.append((0, 0, {
                            'product_id': product.id,
                            'name': line_data.get('name') or product.name,
                            'quantity': line_data.get('quantity', 1.0),
                            'price_unit': line_data.get('price_unit', 0.0),
                            'account_id': account.id,
                            'tax_ids': [(6, 0, tax_ids)] if tax_ids else [(5, 0, 0)],
                        }))

                    except Exception as line_error:
                        _logger.exception("Technical error processing credit note line: %s", str(line_error))
                        return {
                            'success': False,
                            'status': 500,
                            'message': (
                                f"Technical error while processing line for product "
                                f"'{line_data.get('default_code', 'Unknown')}'. "
                                f"Please contact your Odoo administrator. "
                                f"Error: {str(line_error)}"
                            )
                        }

                credit_note_data['invoice_line_ids'] = invoice_lines

                # -------- 6. Create & Post Credit Note --------
                try:
                    env = request.env(user=company.user_ids[0].id if company.user_ids else SUPERUSER_ID)
                    credit_note = env['account.move'].sudo().with_company(company).create(credit_note_data)
                except Exception as create_error:
                    error_str = str(create_error)
                    if self._is_concurrency_conflict(error_str):
                        self._safe_rollback(request.env.cr)
                        _payload_key = id(received_payload)
                        _retries_so_far = _retry_counts.get(_payload_key, 0)
                        if _retries_so_far < _MAX_CONCURRENT_RETRIES:
                            _retry_counts[_payload_key] = _retries_so_far + 1
                            _logger.warning(
                                "Concurrent update conflict creating credit note '%s' "
                                "(retry %d/%d) — requeued.",
                                received_payload.get('tally_credit_note_number', 'Unknown'),
                                _retries_so_far + 1, _MAX_CONCURRENT_RETRIES)
                            time.sleep(0.3)
                            _incoming_cn_datas.append(received_payload)
                            continue
                        _logger.error(
                            "Credit note '%s' failed after %d concurrent-update retries.",
                            received_payload.get('tally_credit_note_number', 'Unknown'),
                            _MAX_CONCURRENT_RETRIES)
                    else:
                        _logger.exception("Technical error while creating credit note: %s", error_str)
                    skipped_credit_notes.append({
                        'tally_credit_note_number': received_payload.get('tally_credit_note_number', 'Unknown'),
                        'reason': error_str,
                    })
                    continue

                try:
                    credit_note.action_post()
                except Exception as post_error:
                    error_str = str(post_error)
                    if self._is_concurrency_conflict(error_str):
                        self._safe_rollback(request.env.cr)
                        _payload_key = id(received_payload)
                        _retries_so_far = _retry_counts.get(_payload_key, 0)
                        if _retries_so_far < _MAX_CONCURRENT_RETRIES:
                            _retry_counts[_payload_key] = _retries_so_far + 1
                            _logger.warning(
                                "Concurrent update conflict posting credit note '%s' "
                                "(retry %d/%d) — requeued.",
                                received_payload.get('tally_credit_note_number', 'Unknown'),
                                _retries_so_far + 1, _MAX_CONCURRENT_RETRIES)
                            time.sleep(0.3)
                            _incoming_cn_datas.append(received_payload)
                            continue
                    _logger.exception("Technical error while posting credit note: %s", error_str)
                    skipped_credit_notes.append({
                        'tally_credit_note_number': received_payload.get('tally_credit_note_number', 'Unknown'),
                        'reason': f"Created but not posted: {error_str}",
                    })
                    continue

                credit_note_numbers.append(credit_note.id)
                tally_credit_note_numbers.append(received_payload.get('tally_credit_note_number'))
                tally_master_ids.append(received_payload.get('tally_master_id'))
                _logger.info("Credit note created: %s for invoice %s", credit_note.name, original_invoice.name)

        # -------- Catch-all --------
        except Exception as e:
            _logger.exception("Unexpected technical error in create_credit_note API: %s", str(e))
            return {
                'success': False,
                'status': 500,
                'message': (
                    f"An unexpected technical error occurred while processing credit note. "
                    f"Please contact your Odoo administrator immediately. "
                    f"Error: {str(e)}"
                )
            }

        return {
            'success': True,
            'status': 200,
            'response': {'CreditNote_Created': credit_note_numbers},
            'message': 'Success' if not skipped_credit_notes else (
                f"Partial success: {len(credit_note_numbers)} created, "
                f"{len(skipped_credit_notes)} skipped."
            ),
            'Tally_credit_note_numbers': tally_credit_note_numbers,
            'Tally_master_ids': tally_master_ids,
            'Skipped_Credit_Notes': skipped_credit_notes,
        }


    @http.route('/web/api/create_debit_note', type='json', auth='none', methods=['POST'], csrf=False)
    def create_debit_note(self, **received_payloads):
        debit_note_numbers = []
        tally_debit_note_numbers = []
        tally_master_ids = []
        skipped_debit_notes = []
        _retry_counts = {}
        _MAX_CONCURRENT_RETRIES = 3
        _incoming_dn_datas = list(received_payloads.get('datas', []))  # mutable — allows requeue on conflict

        try:
            _idx = 0
            while _idx < len(_incoming_dn_datas):
                received_payload = _incoming_dn_datas[_idx]
                _idx += 1

                # -------- Required Fields Check --------
                required_fields = ['tally_debit_note_number', 'tally_master_id']
                missing_fields = [f for f in required_fields if not received_payload.get(f)]
                if missing_fields:
                    return {
                        'success': False,
                        'status': 400,
                        'message': f"Missing required fields: {', '.join(missing_fields)}"
                    }

                if not received_payload.get('original_bill_number') and not received_payload.get('tally_bill_number'):
                    return {
                        'success': False,
                        'status': 400,
                        'message': "Either 'original_bill_number' or 'tally_bill_number' is required."
                    }

                # -------- 1. Authenticate --------
                api_token = received_payloads.get('api_token')
                if not api_token:
                    return {
                        'success': False,
                        'status': 401,
                        'message': 'API Token is required.'
                    }

                try:
                    company = request.env['res.company'].sudo().search([
                        ('api_token', '=', api_token)
                    ], limit=1)
                except Exception as auth_error:
                    _logger.exception("Technical error during authentication: %s", str(auth_error))
                    return {
                        'success': False,
                        'status': 500,
                        'message': (
                            f"Technical error occurred during authentication. "
                            f"Please contact your Odoo administrator. "
                            f"Error: {str(auth_error)}"
                        )
                    }

                if not company:
                    return {
                        'success': False,
                        'status': 401,
                        'message': 'Invalid API Token.'
                    }

                # -------- 2. Duplicate Check --------
                try:
                    duplicate_debit_note = request.env['account.move'].sudo().search([
                        ('tally_invoice_number', '=', received_payload.get('tally_debit_note_number')),
                        ('company_id', '=', company.id),
                        ('move_type', '=', 'in_refund')
                    ], limit=1)
                except Exception as dup_error:
                    _logger.exception("Technical error during duplicate check: %s", str(dup_error))
                    return {
                        'success': False,
                        'status': 500,
                        'message': (
                            f"Technical error occurred while checking for duplicate debit note "
                            f"'{received_payload.get('tally_debit_note_number')}'. "
                            f"Please contact your Odoo administrator. "
                            f"Error: {str(dup_error)}"
                        )
                    }

                if duplicate_debit_note:
                    return {
                        'success': False,
                        'status': 409,
                        'message': (
                            f"Debit note '{received_payload.get('tally_debit_note_number')}' "
                            f"already exists in Odoo as '{duplicate_debit_note.name}'."
                        ),
                        'existing_debit_note': duplicate_debit_note.name
                    }

                # -------- 3. Find Original Vendor Bill --------
                try:
                    original_bill = None

                    if received_payload.get('original_bill_number'):
                        original_bill = request.env['account.move'].sudo().search([
                            ('name', '=', received_payload.get('original_bill_number')),
                            ('company_id', '=', company.id),
                            ('move_type', '=', 'in_invoice'),
                            ('state', '=', 'posted')
                        ], limit=1)

                    if not original_bill and received_payload.get('tally_bill_number'):
                        original_bill = request.env['account.move'].sudo().search([
                            ('tally_invoice_number', '=', received_payload.get('tally_bill_number')),
                            ('company_id', '=', company.id),
                            ('move_type', '=', 'in_invoice'),
                            ('state', '=', 'posted')
                        ], limit=1)

                except Exception as bill_search_error:
                    _logger.exception("Technical error while searching original bill: %s", str(bill_search_error))
                    return {
                        'success': False,
                        'status': 500,
                        'message': (
                            f"Technical error occurred while searching for the original vendor bill. "
                            f"Please contact your Odoo administrator. "
                            f"Error: {str(bill_search_error)}"
                        )
                    }

                if not original_bill:
                    return {
                        'success': False,
                        'status': 404,
                        'message': (
                            f"Original vendor bill not found or not in posted state. "
                            f"Searched by: "
                            f"Odoo number='{received_payload.get('original_bill_number')}', "
                            f"Tally number='{received_payload.get('tally_bill_number')}'."
                        )
                    }

                # -------- 4. Prepare Debit Note Data --------
                debit_note_data = {
                    'move_type': 'in_refund',
                    'partner_id': original_bill.partner_id.id,
                    'company_id': company.id,
                    'currency_id': original_bill.currency_id.id,
                    'invoice_date': received_payload.get('debit_note_date') or fields.Date.today(),
                    'invoice_origin': original_bill.name,
                    'ref': received_payload.get('reason', 'Debit Note'),
                    'tally_invoice_number': received_payload.get('tally_debit_note_number'),
                    'tally_master_id': received_payload.get('tally_master_id'),
                    'company_primary_key': received_payload.get('company_primary_key', ''),
                    'reversed_entry_id': original_bill.id,
                }

                # -------- 5. Build Invoice Lines --------
                invoice_lines = []

                for line_data in received_payload.get('invoice_line_ids', []):
                    try:
                        product = request.env['product.product'].sudo().search([
                            ('default_code', '=', (line_data.get('default_code') or '').strip())
                        ], limit=1)

                        if not product:
                            return {
                                'success': False,
                                'status': 404,
                                'message': f"Product with code '{child_dict.get('default_code')}' and name '{child_dict.get('name')}' not found",
                            }

                        product = product.with_company(company)

                        account = (
                            product.property_account_expense_id
                            or product.categ_id.property_account_expense_categ_id
                        )

                        if not account:
                            return {
                                'success': False,
                                'status': 400,
                                'message': (
                                    f"No expense account configured for product '{product.default_code}'. "
                                    f"Please configure it in Odoo."
                                )
                            }

                        tax_ids = []
                        if line_data.get('tax_list_ids'):
                            try:
                                tax_names = line_data.get('tax_list_ids').split(',')
                                for tax_name in tax_names:
                                    tax = request.env['account.tax'].sudo().search([
                                        ('name', '=', tax_name.strip()),
                                        ('company_id', '=', company.id),
                                        ('type_tax_use', '=', 'purchase')
                                    ], limit=1)
                                    if not tax:
                                        return {
                                            'success': False,
                                            'status': 404,
                                            'message': (
                                                f"Tax '{tax_name.strip()}' not found for company '{company.name}'. "
                                                f"Please configure it in Odoo."
                                            )
                                        }
                                    tax_ids.append(tax.id)
                            except Exception as tax_error:
                                _logger.exception("Technical error processing taxes: %s", str(tax_error))
                                return {
                                    'success': False,
                                    'status': 500,
                                    'message': (
                                        f"Technical error while processing taxes for product '{product.default_code}'. "
                                        f"Please contact your Odoo administrator. "
                                        f"Error: {str(tax_error)}"
                                    )
                                }

                        invoice_lines.append((0, 0, {
                            'product_id': product.id,
                            'name': line_data.get('name') or product.name,
                            'quantity': line_data.get('quantity', 1.0),
                            'price_unit': line_data.get('price_unit', 0.0),
                            'account_id': account.id,
                            'tax_ids': [(6, 0, tax_ids)] if tax_ids else [(5, 0, 0)],
                        }))

                    except Exception as line_error:
                        _logger.exception("Technical error processing debit note line: %s", str(line_error))
                        return {
                            'success': False,
                            'status': 500,
                            'message': (
                                f"Technical error while processing line for product "
                                f"'{line_data.get('default_code', 'Unknown')}'. "
                                f"Please contact your Odoo administrator. "
                                f"Error: {str(line_error)}"
                            )
                        }

                debit_note_data['invoice_line_ids'] = invoice_lines

                # -------- 6. Create & Post Debit Note --------
                try:
                    env = request.env(user=company.user_ids[0].id if company.user_ids else SUPERUSER_ID)
                    debit_note = env['account.move'].sudo().with_company(company).create(debit_note_data)
                except Exception as create_error:
                    error_str = str(create_error)
                    if self._is_concurrency_conflict(error_str):
                        self._safe_rollback(request.env.cr)
                        _payload_key = id(received_payload)
                        _retries_so_far = _retry_counts.get(_payload_key, 0)
                        if _retries_so_far < _MAX_CONCURRENT_RETRIES:
                            _retry_counts[_payload_key] = _retries_so_far + 1
                            _logger.warning(
                                "Concurrent update conflict creating debit note '%s' "
                                "(retry %d/%d) — requeued.",
                                received_payload.get('tally_debit_note_number', 'Unknown'),
                                _retries_so_far + 1, _MAX_CONCURRENT_RETRIES)
                            time.sleep(0.3)
                            _incoming_dn_datas.append(received_payload)
                            continue
                        _logger.error(
                            "Debit note '%s' failed after %d concurrent-update retries.",
                            received_payload.get('tally_debit_note_number', 'Unknown'),
                            _MAX_CONCURRENT_RETRIES)
                    else:
                        _logger.exception("Technical error while creating debit note: %s", error_str)
                    skipped_debit_notes.append({
                        'tally_debit_note_number': received_payload.get('tally_debit_note_number', 'Unknown'),
                        'reason': error_str,
                    })
                    continue

                try:
                    debit_note.action_post()
                except Exception as post_error:
                    error_str = str(post_error)
                    if self._is_concurrency_conflict(error_str):
                        self._safe_rollback(request.env.cr)
                        _payload_key = id(received_payload)
                        _retries_so_far = _retry_counts.get(_payload_key, 0)
                        if _retries_so_far < _MAX_CONCURRENT_RETRIES:
                            _retry_counts[_payload_key] = _retries_so_far + 1
                            _logger.warning(
                                "Concurrent update conflict posting debit note '%s' "
                                "(retry %d/%d) — requeued.",
                                received_payload.get('tally_debit_note_number', 'Unknown'),
                                _retries_so_far + 1, _MAX_CONCURRENT_RETRIES)
                            time.sleep(0.3)
                            _incoming_dn_datas.append(received_payload)
                            continue
                    _logger.exception("Technical error while posting debit note: %s", error_str)
                    skipped_debit_notes.append({
                        'tally_debit_note_number': received_payload.get('tally_debit_note_number', 'Unknown'),
                        'reason': f"Created but not posted: {error_str}",
                    })
                    continue

                debit_note_numbers.append(debit_note.id)
                tally_debit_note_numbers.append(received_payload.get('tally_debit_note_number'))
                tally_master_ids.append(received_payload.get('tally_master_id'))
                _logger.info("Debit note created: %s for bill %s", debit_note.name, original_bill.name)

        # -------- Catch-all --------
        except Exception as e:
            _logger.exception("Unexpected technical error in create_debit_note API: %s", str(e))
            return {
                'success': False,
                'status': 500,
                'message': (
                    f"An unexpected technical error occurred while processing debit note. "
                    f"Please contact your Odoo administrator immediately. "
                    f"Error: {str(e)}"
                )
            }

        return {
            'success': True,
            'status': 200,
            'response': {'DebitNote_Created': debit_note_numbers},
            'message': 'Debit Note(s) created successfully',
            'Tally_debit_note_numbers': tally_debit_note_numbers,
            'Tally_master_ids': tally_master_ids
        }


    @http.route('/web/api/push_product_to_tally', type='json', auth='public', methods=['POST'], csrf=False)
    def push_product_to_tally(self, **kw):
        """
        Push product templates to Tally for one or more companies
        
        Request format:
        {
            "api_token": "YOUR_API_TOKEN",
            "company_ids": [1, 2, 3] or "all",
            "product_tmpl_ids": [10, 20, 30],
            "product_codes": ["PROD001", "PROD002"],  # Alternative
        }
        """
        try:
            # Validate API token
            api_token = kw.get('api_token')
            if not api_token:
                return {
                    'success': False,
                    'message': 'API Token is required',
                    'status': 401
                }
            
            # Get requesting company
            requesting_company = request.env['res.company'].sudo().search([
                ('api_token', '=', api_token)
            ], limit=1)
            
            if not requesting_company:
                return {
                    'success': False,
                    'message': 'Invalid API Token',
                    'status': 401
                }
            
            # Get target companies
            target_companies = self._get_target_companies(kw, requesting_company)
            
            if not target_companies:
                return {
                    'success': False,
                    'message': 'No valid companies found with Tally configuration',
                    'status': 400
                }
            
            # Get product templates
            products = self._get_products(kw)
            
            if not products:
                return {
                    'success': False,
                    'message': 'No products found',
                    'status': 400
                }

            update_existing = kw.get('update_existing', True)     
            
            # Push to Tally
            results = self._push_to_tally(products, target_companies)
            
            return {
                    'success': True,
                    'status': 200,
                    'message': f'Processed {len(products)} products for {len(target_companies)} companies',
                    'summary': {
                        'total_products': len(products),
                        'total_companies': len(target_companies),
                        'successful': len(results['success']),
                        'updated': len(results['updated']),
                        'failed': len(results['failed'])
                    },
                    'details': results
                }
            
        except Exception as e:
            _logger.error(f"API Error: {str(e)}", exc_info=True)
            return {'success': False, 'message': str(e), 'status': 500}

    
    def _get_target_companies(self, kw, requesting_company):
        """Get companies to push to"""
        company_ids = kw.get('company_ids')
        
        if company_ids == "all" or not company_ids:
            return request.env['res.company'].sudo().search([
                ('tally_url', '!=', False)
            ])
        else:
            return request.env['res.company'].sudo().browse(company_ids).filtered(
                lambda c: c.tally_url
            )
    

    def _get_products(self, kw):
        domain = []

        # Created after (MAIN requirement)
        if kw.get('created_after'):
            domain.append(('create_date', '>=', kw['created_after']))

        # Optional: updated after
        if kw.get('updated_after'):
            domain.append(('write_date', '>=', kw['updated_after']))

        # Optional: specific products
        if kw.get('product_tmpl_ids'):
            return request.env['product.template'].sudo().browse(
                kw['product_tmpl_ids']
            )

        # Optional: product codes
        if kw.get('product_codes'):
            codes = kw['product_codes']
            if isinstance(codes, str):
                codes = [codes]
            domain.append(('default_code', 'in', codes))

        return request.env['product.template'].sudo().search(domain)

    def _decide_tally_action(self, product, company):
        if company in product.tally_company_ids:
            return 'Alter'
        return 'Create'
    

    
    def _push_to_tally(self, products, companies, update_existing=True):
        """Enhanced push with update tracking"""
        results = {
            'success': [],
            'failed': [],
            'updated': []
        }
        
        for company in companies:
            for product in products:
                try:
                    result = self._push_single_product(product, company, update_existing)
                    
                    if result['success']:
                        product.sudo().write({
                            'tally_sync_status': 'synced',
                            'tally_sync_date': fields.Datetime.now(),
                            'tally_sync_error': False,
                            'tally_company_ids': [(4, company.id)],
                            'tally_product_name': product.name
                        })
                        
                        result_data = {
                            'product_id': product.id,
                            'product_code': product.default_code,
                            'product_name': product.name,
                            'company_id': company.id,
                            'company_name': company.name,
                        }
                        
                        if result.get('action') == 'Alter':
                            results['updated'].append(result_data)
                        else:
                            results['success'].append(result_data)
                    else:
                        product.sudo().write({
                            'tally_sync_status': 'failed',
                            'tally_sync_error': result.get('message')
                        })
                        
                        results['failed'].append({
                            'product_id': product.id,
                            'product_code': product.default_code,
                            'product_name': product.name,
                            'company_id': company.id,
                            'company_name': company.name,
                            'error': result.get('message')
                        })
                        
                except Exception as e:
                    results['failed'].append({
                        'product_id': product.id,
                        'product_code': product.default_code,
                        'product_name': product.name,
                        'company_id': company.id,
                        'company_name': company.name,
                        'error': str(e)
                    })
        
        return results
    
    def _push_single_product(self, product, company, update_existing=True):
        """Push single product template to Tally with update support"""
        try:
            product_data = {
                'default_code': product.default_code or product.name[:20],
                'name': product.name,
                'category': product.categ_id.name or 'Primary',
                'uom': product.uom_id.name or 'Nos',
                'price': product.list_price or 0.0,
            }
            
            # Determine if this is CREATE or ALTER
            action = 'Create'
            if update_existing and product.is_in_tally and company in product.tally_company_ids:
                action = 'Alter'  # Tally uses 'Alter' to update existing items
            
            xml_data = self._prepare_tally_xml(product_data, action=action)
            
            response = requests.post(
                company.tally_url,
                data=xml_data.encode('utf-8'),
                headers={'Content-Type': 'application/xml; charset=utf-8'},
                timeout=10
            )
            
            if response.status_code == 200 and "1" in response.text:
                return {'success': True, 'action': action}
            else:
                return {
                    'success': False,
                    'message': f'Tally error: {response.text[:200]}'
                }
                
        except Exception as e:
            return {'success': False, 'message': str(e)}

    

    @http.route('/web/api/get_products', type='json', auth='none', methods=['POST'], csrf=False)
    def get_product_master(self, **kw):
        """
        Fetch product master data from Odoo to sync with Tally.

        Request payload example:
        {
            "api_token": "your_company_api_token",
            "company_primary_key": "your_company_key",
            "filters": {
                "active": true,
                "product_type": "consu",       // optional: 'consu', 'service', 'product'
                "default_code": "PROD001",      // optional: filter by internal ref
                "categ_id": 5,                  // optional: filter by category ID
                "updated_after": "2025-01-01"   // optional: fetch products updated after date
            },
            "limit": 100,                        // optional: default 100
            "offset": 0                          // optional: for pagination
        }

        Response:
        {
            "success": true,
            "status": 200,
            "message": "Success",
            "total_count": 50,
            "products": [
                {
                    "id": 1,
                    "name": "Product Name",
                    "default_code": "PROD001",
                    "barcode": "1234567890",
                    "product_type": "consu",
                    "uom_name": "Unit(s)",
                    "sales_price": 100.0,
                    "standard_price": 80.0,
                    "tax_ids": [{"id": 1, "name": "GST 18%", "amount": 18.0}],
                    "categ_name": "All",
                    "active": true,
                    "description": "Product description",
                    "income_account": {"id": 1, "name": "Sales Account", "code": "400000"},
                    "expense_account": {"id": 2, "name": "Purchase Account", "code": "500000"},
                    "write_date": "2025-01-01 12:00:00"
                }
            ]
        }
        """

        # ------------------------------------------------------------------
        # 1. Validate API token
        # ------------------------------------------------------------------
        api_token = kw.get('api_token')
        if not api_token:
            return {
                'success': False,
                'status': 401,
                'message': 'API Token is required'
            }

        company = request.env['res.company'].sudo().search(
            [('api_token', '=', api_token)], limit=1
        )
        if not company:
            return {
                'success': False,
                'status': 401,
                'message': 'Invalid API Token'
            }

        # ------------------------------------------------------------------
        # 2. Build search domain
        # ------------------------------------------------------------------
        filters = kw.get('filters', {})
        domain = [('company_id', '=', company.id)]

        # Active filter (default: only active)
        active_filter = filters.get('active', True)
        if active_filter is not None:
            domain.append(('active', '=', active_filter))

        # Product type filter: 'consu', 'service', 'product'
        if filters.get('product_type'):
            domain.append(('type', '=', filters['product_type']))

        # Filter by internal reference
        if filters.get('default_code'):
            domain.append(('default_code', '=', filters['default_code']))

        # Filter by category
        if filters.get('categ_id'):
            domain.append(('categ_id', '=', int(filters['categ_id'])))

        # Filter by last updated date (for incremental sync to Tally)
        if filters.get('updated_after'):
            domain.append(('write_date', '>=', filters['updated_after']))

        # ------------------------------------------------------------------
        # 3. Pagination
        # ------------------------------------------------------------------
        limit  = int(kw.get('limit', 100))
        offset = int(kw.get('offset', 0))

        # ------------------------------------------------------------------
        # 4. Fetch products with company context
        # ------------------------------------------------------------------
        safe_env = request.env(
            user=SUPERUSER_ID,
            context={
                **request.env.context,
                'allowed_company_ids': [company.id],
                'force_company': company.id,
            }
        )

        ProductTemplate = safe_env['product.template'].with_company(company)

        total_count = ProductTemplate.search_count(domain)
        products    = ProductTemplate.search(domain, limit=limit, offset=offset,
                                             order='write_date desc')

        # ------------------------------------------------------------------
        # 5. Build response
        # ------------------------------------------------------------------
        product_list = []
        for product in products:
            # Income account (sales)
            income_account = (
                product.property_account_income_id
                or product.categ_id.property_account_income_categ_id
            )

            # Expense account (purchase)
            expense_account = (
                product.property_account_expense_id
                or product.categ_id.property_account_expense_categ_id
            )

            # Taxes on sales
            tax_data = []
            for tax in product.taxes_id.filtered(lambda t: t.company_id.id == company.id):
                tax_data.append({
                    'id':     tax.id,
                    'name':   tax.name,
                    'amount': tax.amount,
                    'type':   tax.amount_type,   # 'percent', 'fixed', etc.
                })

            # Supplier taxes
            supplier_tax_data = []
            for tax in product.supplier_taxes_id.filtered(lambda t: t.company_id.id == company.id):
                supplier_tax_data.append({
                    'id':     tax.id,
                    'name':   tax.name,
                    'amount': tax.amount,
                    'type':   tax.amount_type,
                })

            product_list.append({
                # Identifiers
                'id':               product.id,
                'name':             product.name,
                'default_code':     product.default_code or '',
                'barcode':          product.barcode or '',

                # Type & Category
                'product_type':     product.type,           # consu / service / product
                'categ_id':         product.categ_id.id,
                'categ_name':       product.categ_id.complete_name or product.categ_id.name,

                # Unit of Measure
                'uom_id':           product.uom_id.id,
                'uom_name':         product.uom_id.name,
                'uom_po_id':        product.uom_po_id.id,
                'uom_po_name':      product.uom_po_id.name,

                # Pricing
                'sales_price':      product.list_price,
                'standard_price':   product.standard_price,

                # Taxes
                'tax_ids':          tax_data,
                'supplier_tax_ids': supplier_tax_data,

                # Accounts
                'income_account':  {
                    'id':   income_account.id   if income_account  else None,
                    'name': income_account.name if income_account  else None,
                    'code': income_account.code if income_account  else None,
                },
                'expense_account': {
                    'id':   expense_account.id   if expense_account else None,
                    'name': expense_account.name if expense_account else None,
                    'code': expense_account.code if expense_account else None,
                },

                # Meta
                'active':           product.active,
                'description':      product.description or '',
                'description_sale': product.description_sale or '',
                'description_purchase': product.description_purchase or '',
                'write_date':       str(product.write_date),
                'create_date':      str(product.create_date),
            })

        return {
            'success':     True,
            'status':      200,
            'message':     'Success',
            'company':     company.name,
            'total_count': total_count,
            'limit':       limit,
            'offset':      offset,
            'products':    product_list,
        }        


   
    @http.route('/web/api/create_draft_partner',type="json",auth='none',methods=['POST'])
    def draft_partner(self,**kw):
        
        claim_obj = validations.API.draftpartner(kw.get('mobile'))
        if claim_obj:
            return {'success':False,'response':{'message':'draft partner already exist in this mobile number','status':200}} 
                    
                
        
        contact_fields = request.env['draft.partner'].sudo().fields_get()
        mandatory_fields = []


        #remove unwanted keys
        processed_dict = validations.API.RemoveUnwantedKeys(kw)
        
        response = validations.API.FieldValidation(contact_fields,processed_dict,mandatory_fields)
        
        if response:
            return response
            


        else:
            # if processed_dict:
            partner_obj = request.env['draft.partner'].sudo().create(processed_dict)
            if partner_obj:
                if partner_obj.is_plumber != True:
                    partner_obj.write({'is_retailer':True})
            return {'success':True,'odoo_partner_id':partner_obj.id,'message':'draft contact created','status':200}


    @http.route('/web/api/update_draft_partner',type="json",auth='none',methods=['POST'])
    def update_draft_partner(self,**kw):
        draft_partner_obj = request.env['draft.partner'].sudo().search([('mobile','=',kw.get('mobile'))])
        if draft_partner_obj:
            draft_partner_obj.write({'kyc_type_id':kw.get('kyc_type_id'),'kyc_number':kw.get('kyc_number'),'state':'kyc_to_approve'})


            return {'success':True,'message':'kyc details updated ','status':200}

        else:
            return {'success':True,'message':'draft contact not created','status':200}




    # ══════════════════════════════════════════════════════════════════════════
    # VENDOR BILL API  —  /web/api/create_vendor_bill
    # Identical flow to create_invoice but:
    #   • move_type  = 'in_invoice'   (sits in Vendor Bills screen)
    #   • account    = property_account_expense_id  (not income)
    #   • taxes      = type_tax_use = 'purchase'    (not sale)
    # ══════════════════════════════════════════════════════════════════════════

    def _resolve_tally_tax_purchase(self, tax_item, company):
        """Same logic as _resolve_tally_tax but searches purchase taxes."""
        import re

        tax_item_clean = tax_item.strip()
        tax_upper = tax_item_clean.upper()

        is_igst = any(kw in tax_upper for kw in [
            'IGST', 'INTEGRATED', 'INTEGRATED TAX', 'INTER STATE', 'INTER-STATE'
        ])
        is_exempt = any(kw in tax_upper for kw in [
            'EXEMPT', 'NIL', 'NON GST', 'NON-GST', 'NONGST', 'NGST', 'NOT APPLICABLE'
        ])

        match = re.search(r'@?\s*(\d+(?:\.\d+)?)\s*%', tax_item_clean)
        if not match:
            match = re.search(r'(?:^|[\s@])(\d+(?:\.\d+)?)\s*$', tax_item_clean)

        if is_exempt or (match and match.group(1) == '0'):
            candidate_names = ['0% Exempt', '0%', '0% NGST', '0% IGST S']
        elif not match:
            tax = request.env['account.tax'].sudo().search([
                ('name', '=', tax_item_clean),
                ('company_id', '=', company.id),
                ('type_tax_use', '=', 'purchase')
            ], limit=1)
            if tax:
                return [tax.id], None
            return [], {
                'success': False,
                'message': f"Tax '{tax_item}' from Tally could not be matched for purchase.",
                'status': 400
            }
        else:
            percent = match.group(1).rstrip('0').rstrip('.') if '.' in match.group(1) else match.group(1)
            try:
                percent = str(int(float(percent))) if float(percent) == int(float(percent)) else percent
            except Exception:
                pass

            if is_igst:
                candidate_names = [
                    f"{percent}% IGST S", f"{percent}% IGST",
                    f"IGST {percent}%", f"IGST@{percent}%",
                ]
            else:
                candidate_names = [
                    f"{percent}% GST", f"{percent}% GST S",
                    f"GST {percent}%", f"GST@{percent}%",
                    f"{percent}%",
                ]

        for odoo_tax_name in candidate_names:
            tax = request.env['account.tax'].sudo().search([
                ('name', '=', odoo_tax_name),
                ('company_id', '=', company.id),
                ('type_tax_use', '=', 'purchase')
            ], limit=1)
            if tax:
                _logger.info("✓ Tally purchase tax '%s' → matched '%s' (id:%s)",
                             tax_item, tax.name, tax.id)
                return [tax.id], None

        available_taxes = request.env['account.tax'].sudo().search([
            ('company_id', '=', company.id),
            ('type_tax_use', '=', 'purchase')
        ]).mapped('name')

        return [], {
            'success': False,
            'message': (
                f"Purchase tax '{tax_item}' from Tally could not be matched in Odoo "
                f"for company '{company.name}'. "
                f"Tried: {candidate_names}. "
                f"Available purchase taxes: {available_taxes}"
            ),
            'status': 404
        }

    @http.route('/web/api/create_vendor_bill', type='json', auth='none', methods=['POST'], csrf=False)
    def accountmove_vendor_bill(self, **received_payloads):
        """
        Create vendor bills (in_invoice) from Tally.
        Payload is identical to create_invoice — just send to this endpoint
        and the bill will land in Odoo's Vendor Bills screen.

        Key differences vs create_invoice:
          • move_type = 'in_invoice'
          • Uses expense account (property_account_expense_id) per line
          • Uses purchase taxes (type_tax_use = 'purchase')
        """
        bill_numbers       = []
        tally_bill_numbers = []
        tally_master_ids   = []

        try:
            for received_payload in received_payloads.get('datas', []):

                # ── Auth ──────────────────────────────────────────────────
                api_token = received_payloads.get('api_token')
                if not api_token:
                    return {'success': False, 'message': 'API Token is required', 'status': 401}

                company = request.env['res.company'].sudo().search([
                    ('api_token', '=', api_token)
                ], limit=1)
                if not company:
                    return {'success': False, 'message': 'Invalid API Token', 'status': 401}

                # ── Duplicate check ────────────────────────────────────────
                tally_bill_no = received_payload.get('tally_invoice_number')
                duplicate = request.env['account.move'].sudo().search([
                    ('tally_invoice_number', '=', tally_bill_no),
                    ('company_id', '=', company.id),
                    ('move_type', '=', 'in_invoice'),
                ], limit=1)

                if duplicate:
                    _logger.info("Vendor bill duplicate '%s' → updating.", tally_bill_no)
                    # Reset to draft, replace lines, re-post
                    try:
                        with request.env.cr.savepoint():
                            inv = duplicate.sudo()
                            if inv.state != 'draft':
                                inv.button_draft()
                            line_commands, err = self._build_vendor_bill_lines(
                                received_payload.get('invoice_line_ids', []), company, as_commands=False)
                            if err:
                                return err
                            inv.write({
                                'invoice_origin': received_payload.get('invoice_origin'),
                                'invoice_line_ids': line_commands,
                            })
                            inv.action_post()

                        # ── Reverse old receipt and create new one ────────
                        # Find existing receipt linked to this bill
                        old_pickings = request.env['stock.picking'].sudo().search([
                            ('origin', '=', duplicate.name),
                            ('picking_type_code', '=', 'incoming'),
                            ('state', '=', 'done'),
                            ('company_id', '=', company.id),
                        ])
                        for old_pick in old_pickings:
                            try:
                                # Create a return (reverse) for the old receipt
                                return_wizard = request.env['stock.return.picking'].sudo().with_context(
                                    active_id=old_pick.id,
                                    active_model='stock.picking'
                                ).create({'picking_id': old_pick.id})
                                return_pick_id = return_wizard.create_returns()
                                return_pick = request.env['stock.picking'].sudo().browse(
                                    return_pick_id['res_id'])
                                # Validate the return immediately
                                for move in return_pick.move_ids:
                                    move.quantity = move.product_uom_qty
                                return_pick.with_context(
                                    skip_backorder=True,
                                    immediate_transfer=True,
                                ).button_validate()
                                _logger.info(
                                    "Reversed old receipt '%s' for updated bill '%s'",
                                    old_pick.name, tally_bill_no)
                            except Exception as re:
                                _logger.warning(
                                    "Could not reverse old receipt '%s': %s",
                                    old_pick.name, str(re))

                        # Create fresh receipt with new quantities
                        try:
                            new_receipt = self._create_and_validate_receipt(
                                duplicate, received_payload, company)
                            if isinstance(new_receipt, dict):
                                _logger.warning(
                                    "Updated bill '%s' — new receipt failed: %s",
                                    tally_bill_no, new_receipt.get('message'))
                            elif new_receipt:
                                _logger.info(
                                    "✓ New receipt '%s' created for updated bill '%s'",
                                    new_receipt.name, tally_bill_no)
                        except Exception as re:
                            _logger.warning(
                                "New receipt failed for updated bill '%s': %s",
                                tally_bill_no, str(re))

                    except Exception as ue:
                        self._safe_rollback(request.env.cr)
                        return {'success': False, 'message': str(ue), 'status': 500}

                    bill_numbers.append(duplicate.id)
                    tally_bill_numbers.append(tally_bill_no)
                    tally_master_ids.append(received_payload.get('tally_master_id'))
                    continue

                # ── Build line commands ────────────────────────────────────
                line_commands, err = self._build_vendor_bill_lines(
                    received_payload.get('invoice_line_ids', []), company)
                if err:
                    return err

                if not line_commands:
                    return {
                        'success': False,
                        'message': (f"Vendor bill '{tally_bill_no}' not created — "
                                    f"no valid lines found."),
                        'status': 400
                    }

                # ── Resolve vendor (partner) ───────────────────────────────
                vendor_name = received_payload.get('customer_name') or received_payload.get('vendor_name')
                partner = None
                if received_payload.get('vat'):
                    partner = request.env['res.partner'].sudo().search([
                        ('vat', '=', received_payload['vat']),
                        ('company_id', 'in', [company.id, False])
                    ], limit=1)
                if not partner and vendor_name:
                    partner = request.env['res.partner'].sudo().search([
                        ('name', 'ilike', vendor_name),
                        ('company_id', 'in', [company.id, False])
                    ], limit=1)
                if not partner and vendor_name:
                    # Auto-create vendor
                    partner = request.env['res.partner'].sudo().create({
                        'name': vendor_name,
                        'vat': self._clean_gstin(received_payload.get('vat', '')),
                        'street': received_payload.get('street', ''),
                        'street2': received_payload.get('street2', ''),
                        'city': received_payload.get('city', ''),
                        'zip': received_payload.get('zip', ''),
                        'company_id': False,
                        'supplier_rank': 1,
                    })

                if not partner:
                    return {
                        'success': False,
                        'message': f"Vendor '{vendor_name}' not found and could not be created.",
                        'status': 404
                    }

                # ── Create vendor bill ─────────────────────────────────────
                try:
                    with request.env.cr.savepoint():
                        bill_vals = {
                            'move_type':           'in_invoice',   # ← THIS is what makes it a vendor bill
                            'partner_id':          partner.id,
                            'company_id':          company.id,
                            'invoice_date':        received_payload.get('invoice_date'),
                            'invoice_origin':      received_payload.get('invoice_origin', ''),
                            'ref':                 tally_bill_no,
                            'tally_invoice_number': tally_bill_no,
                            'tally_master_id':     received_payload.get('tally_master_id', ''),
                            'company_primary_key': received_payload.get('company_primary_key', ''),
                            'invoice_line_ids':    line_commands,
                        }
                        env = request.env(
                            user=company.user_ids[0].id if company.user_ids else SUPERUSER_ID)
                        bill = env['account.move'].sudo().with_company(company).create(bill_vals)
                        bill.action_post()

                    # ── Create and validate stock receipt ─────────────────
                    # IMPORTANT: outside the savepoint so receipt failure
                    # never rolls back the already-posted bill.
                    try:
                        receipt = self._create_and_validate_receipt(
                            bill, received_payload, company)
                        if isinstance(receipt, dict):
                            _logger.warning(
                                "Vendor bill '%s' created but receipt failed: %s",
                                tally_bill_no, receipt.get('message'))
                        elif receipt:
                            _logger.info(
                                "✓ Receipt '%s' validated for vendor bill '%s'",
                                receipt.name, tally_bill_no)
                    except Exception as re:
                        _logger.warning(
                            "Receipt creation failed for bill '%s' (non-fatal): %s",
                            tally_bill_no, str(re))

                    bill_numbers.append(bill.id)
                    tally_bill_numbers.append(tally_bill_no)
                    tally_master_ids.append(received_payload.get('tally_master_id'))
                    _logger.info("✓ Vendor bill '%s' created (id:%s)", tally_bill_no, bill.id)

                except Exception as ce:
                    _logger.exception("Error creating vendor bill '%s': %s", tally_bill_no, ce)
                    self._safe_rollback(request.env.cr)
                    return {
                        'success': False,
                        'message': f"Error creating vendor bill '{tally_bill_no}': {str(ce)}",
                        'status': 500
                    }

        except Exception as e:
            _logger.exception("Unexpected error in create_vendor_bill: %s", e)
            self._safe_rollback(request.env.cr)
            return {'success': False, 'message': str(e), 'status': 500}

        return {
            'success': True,
            'status': 200,
            'message': 'Vendor bill(s) created successfully',
            'response': {'Bills_Created': bill_numbers},
            'Tally_bill_numbers': tally_bill_numbers,
            'Tally_Master_Ids': tally_master_ids,
        }

    def _build_vendor_bill_lines(self, invoice_line_ids, company, as_commands=True):
        """
        Build account.move.line commands for vendor bills.
        Uses expense account and purchase taxes — opposite of _build_invoice_lines.
        """
        lines = []
        for child_dict in invoice_line_ids:
            default_code = (child_dict.get('default_code') or '').strip()
            if not default_code:
                _logger.warning("Vendor bill line skipped — no default_code for '%s'",
                                child_dict.get('name'))
                continue

            product = request.env['product.product'].sudo().search([
                ('default_code', '=', default_code)
            ], limit=1)

            if not product:
                return None, {
                    'success': False,
                    'message': f"Product with code '{default_code}' not found.",
                    'status': 404
                }

            product = product.with_company(company)

            # ── Keep product cost price in sync with Tally's purchase rate ──
            # Without a real cost price, Odoo can never calculate stock
            # valuation correctly — every stock_valuation_layer entry ends up
            # worth ₹0 even though real quantities are moving (confirmed:
            # Stock Valuation report showing thousands of moves all at
            # ₹0.00). Tally sends the purchase rate as price_unit on every
            # vendor bill line, so we use it to keep the product's cost
            # price current. This makes FUTURE stock movements carry real
            # value automatically — no manual product-by-product entry.
            _tally_cost = child_dict.get('price_unit', 0.0)
            try:
                _tally_cost = float(_tally_cost)
            except (TypeError, ValueError):
                _tally_cost = 0.0

            if _tally_cost > 0 and abs(product.standard_price - _tally_cost) > 0.001:
                try:
                    product.product_tmpl_id.sudo().with_company(company).write({
                        'standard_price': _tally_cost
                    })
                    _logger.info(
                        "Updated cost price for product '%s': %.2f -> %.2f "
                        "(from Tally vendor bill)",
                        default_code, product.standard_price, _tally_cost)
                except Exception as cost_err:
                    # Never let a cost-price update failure block the actual
                    # vendor bill from being created — this is a secondary
                    # enhancement, not a hard requirement for the bill itself.
                    _logger.warning(
                        "Could not update cost price for product '%s': %s",
                        default_code, str(cost_err))

            # ── EXPENSE account (purchase side) ───────────────────────────
            account = (
                product.property_account_expense_id
                or product.categ_id.property_account_expense_categ_id
            )
            if not account:
                return None, {
                    'success': False,
                    'message': (f"No expense account configured for product '{default_code}'. "
                                f"Please set it in the product or product category."),
                    'status': 400
                }

            # ── PURCHASE taxes ─────────────────────────────────────────────
            tax_list_ids = child_dict.get('tax_list_ids', [])
            if tax_list_ids:
                if not isinstance(tax_list_ids, list):
                    tax_list_ids = [tax_list_ids]
                resolved = []
                for tax_item in tax_list_ids:
                    if isinstance(tax_item, int):
                        resolved.append(tax_item)
                    elif isinstance(tax_item, str):
                        ids, err = self._resolve_tally_tax_purchase(tax_item, company)
                        if err:
                            return None, err
                        resolved.extend(ids)
                tax_cmd = [(6, 0, resolved)] if resolved else [(5, 0, 0)]
            else:
                tax_cmd = [(5, 0, 0)]

            lines.append({
                'product_id': product.id,
                'name':       child_dict.get('name') or product.name,
                'quantity':   child_dict.get('quantity', 1),
                'price_unit': child_dict.get('price_unit', 0.0),
                'account_id': account.id,
                'discount':   child_dict.get('discount', 0.0),
                'tax_ids':    tax_cmd,
            })

        if not lines:
            return [], None

        if as_commands:
            return [(0, 0, d) for d in lines], None
        else:
            return [(5, 0, 0)] + [(0, 0, d) for d in lines], None


    # ══════════════════════════════════════════════════════════════════════════
    # SMART SINGLE ENDPOINT  —  /web/api/sync_voucher
    #
    # Tally sends its own voucher_type — this endpoint auto-routes to the
    # correct move_type without any Tally-side XML changes needed.
    #
    # Tally voucher_type  →  Odoo move_type  →  Screen
    # ─────────────────────────────────────────────────────────────────────────
    # Sales               →  out_invoice     →  Customer Invoices
    # Purchase            →  in_invoice      →  Vendor Bills
    # Credit Note         →  out_refund      →  Customer Credit Notes
    # Debit Note          →  in_refund       →  Vendor Debit Notes (Refunds)
    # ══════════════════════════════════════════════════════════════════════════

    # Map every Tally voucher type string → Odoo move_type
    TALLY_VOUCHER_MAP = {
        # Sales variants
        'sales':              'out_invoice',
        'sales invoice':      'out_invoice',
        'tax invoice':        'out_invoice',
        'sales order':        'out_invoice',

        # Purchase variants
        'purchase':           'in_invoice',
        'purchase invoice':   'in_invoice',
        'purchase order':     'in_invoice',
        'vendor bill':        'in_invoice',
        'bill':               'in_invoice',

        # Credit note variants (customer return)
        'credit note':        'out_refund',
        'sales return':       'out_refund',
        'credit memo':        'out_refund',

        # Debit note variants (vendor return / purchase return)
        'debit note':         'in_refund',
        'purchase return':    'in_refund',
        'debit memo':         'in_refund',
    }

    def _resolve_move_type(self, received_payload):
        """
        Determine Odoo move_type from the payload.
        Priority:
          1. explicit 'move_type' field (Tally sends it directly)
          2. 'voucher_type' field mapped through TALLY_VOUCHER_MAP
          3. 'vch_type' field (Tally's internal key)
          4. default → 'out_invoice' (backwards-compatible)
        """
        # 1. Direct move_type
        if received_payload.get('move_type') in (
            'out_invoice', 'in_invoice', 'out_refund', 'in_refund'
        ):
            return received_payload['move_type'], None

        # 2. voucher_type string
        vt = (
            received_payload.get('voucher_type')
            or received_payload.get('vch_type')
            or received_payload.get('VoucherType')
            or ''
        ).strip().lower()

        if vt:
            move_type = self.TALLY_VOUCHER_MAP.get(vt)
            if move_type:
                _logger.info(
                    "sync_voucher: voucher_type='%s' → move_type='%s'",
                    vt, move_type
                )
                return move_type, None
            else:
                return None, {
                    'success': False,
                    'status': 400,
                    'message': (
                        f"Unknown voucher_type '{vt}'. "
                        f"Supported values: {list(self.TALLY_VOUCHER_MAP.keys())}. "
                        f"Alternatively send 'move_type' directly as one of: "
                        f"out_invoice, in_invoice, out_refund, in_refund."
                    )
                }

        # 3. Default fallback — treat as customer invoice (legacy behaviour)
        _logger.warning(
            "sync_voucher: no voucher_type or move_type in payload → "
            "defaulting to out_invoice"
        )
        return 'out_invoice', None

    @http.route('/web/api/sync_voucher', type='json', auth='none', methods=['POST'], csrf=False)
    def sync_voucher(self, **received_payloads):
        """
        Universal Tally → Odoo voucher sync endpoint.

        Tally just needs to send 'voucher_type' (its own field) and this
        endpoint routes each voucher to the correct Odoo document type.

        Minimal payload example:
        {
            "api_token": "xxx",
            "datas": [
                {
                    "voucher_type": "Purchase",        ← Tally's own field
                    "tally_invoice_number": "PUR/001",
                    "vendor_name": "Supplier Ltd",
                    "vat": "29AABCV2840F1ZE",
                    "invoice_date": "2026-05-27",
                    "invoice_line_ids": [...]
                },
                {
                    "voucher_type": "Sales",           ← same endpoint, different type
                    "tally_invoice_number": "SAL/001",
                    "customer_name": "Customer Ltd",
                    "invoice_line_ids": [...]
                }
            ]
        }
        """
        results = []

        try:
            for received_payload in received_payloads.get('datas', []):

                # ── Auth ──────────────────────────────────────────────────
                api_token = received_payloads.get('api_token')
                if not api_token:
                    return {'success': False, 'message': 'API Token is required', 'status': 401}

                company = request.env['res.company'].sudo().search([
                    ('api_token', '=', api_token)
                ], limit=1)
                if not company:
                    return {'success': False, 'message': 'Invalid API Token', 'status': 401}

                # ── Detect move_type ──────────────────────────────────────
                move_type, err = self._resolve_move_type(received_payload)
                if err:
                    return err

                tally_ref = received_payload.get('tally_invoice_number')
                _logger.info(
                    "sync_voucher: processing '%s' as move_type='%s'",
                    tally_ref, move_type
                )

                # ── Route to correct handler ──────────────────────────────
                if move_type == 'out_invoice':
                    result = self._handle_out_invoice(
                        received_payload, received_payloads, company)

                elif move_type == 'in_invoice':
                    result = self._handle_in_invoice(
                        received_payload, company)

                elif move_type == 'out_refund':
                    result = self._handle_out_refund(
                        received_payload, company)

                elif move_type == 'in_refund':
                    result = self._handle_in_refund(
                        received_payload, company)

                else:
                    result = {
                        'tally_ref': tally_ref,
                        'success': False,
                        'message': f"Unsupported move_type '{move_type}'",
                    }

                if result.get('success') is False and result.get('status', 200) >= 400:
                    # Hard error on one voucher — abort whole batch
                    return result

                results.append(result)

        except Exception as e:
            _logger.exception("Unexpected error in sync_voucher: %s", e)
            self._safe_rollback(request.env.cr)
            return {'success': False, 'message': str(e), 'status': 500}

        return {
            'success': True,
            'status': 200,
            'message': f"{len(results)} voucher(s) processed successfully",
            'results': results,
        }

    # ── Individual move_type handlers ──────────────────────────────────────

    def _handle_out_invoice(self, payload, full_payload, company):
        """Customer invoice — delegates to existing create_invoice logic."""
        tally_ref = payload.get('tally_invoice_number')
        # Check duplicate
        duplicate = request.env['account.move'].sudo().search([
            ('tally_invoice_number', '=', tally_ref),
            ('company_id', '=', company.id),
            ('move_type', '=', 'out_invoice'),
        ], limit=1)

        if duplicate:
            err = self._update_move(duplicate, payload, company)
            if err:
                return err
            return {'tally_ref': tally_ref, 'success': True,
                    'action': 'updated', 'odoo_id': duplicate.id,
                    'odoo_name': duplicate.name, 'move_type': 'out_invoice'}

        # Re-use the full invoice creation flow
        temp_payloads = {'api_token': full_payload.get('api_token'), 'datas': [payload]}
        result = self.accountmove_invoice(**temp_payloads)
        if result.get('success'):
            ids = result.get('response', {}).get('Invoice_Created', [])
            move = request.env['account.move'].sudo().browse(ids[0]) if ids else None
            return {'tally_ref': tally_ref, 'success': True,
                    'action': 'created', 'odoo_id': ids[0] if ids else None,
                    'odoo_name': move.name if move else '',
                    'move_type': 'out_invoice'}
        return result

    def _handle_in_invoice(self, payload, company):
        """Vendor bill — uses expense account + purchase taxes."""
        tally_ref = payload.get('tally_invoice_number')
        duplicate = request.env['account.move'].sudo().search([
            ('tally_invoice_number', '=', tally_ref),
            ('company_id', '=', company.id),
            ('move_type', '=', 'in_invoice'),
        ], limit=1)

        if duplicate:
            err = self._update_move(duplicate, payload, company,
                                    tax_type='purchase')
            if err:
                return err
            return {'tally_ref': tally_ref, 'success': True,
                    'action': 'updated', 'odoo_id': duplicate.id,
                    'odoo_name': duplicate.name, 'move_type': 'in_invoice'}

        # Resolve vendor
        partner, err = self._resolve_partner(payload, company, supplier=True)
        if err:
            return err

        line_commands, err = self._build_move_lines(
            payload.get('invoice_line_ids', []), company,
            account_type='expense', tax_type='purchase')
        if err:
            return err
        if not line_commands:
            return {'success': False, 'status': 400,
                    'message': f"No valid lines for vendor bill '{tally_ref}'."}

        bill = self._create_and_post_move({
            'move_type':            'in_invoice',
            'partner_id':           partner.id,
            'company_id':           company.id,
            'invoice_date':         payload.get('invoice_date'),
            'invoice_origin':       payload.get('invoice_origin', ''),
            'ref':                  tally_ref,
            'tally_invoice_number': tally_ref,
            'tally_master_id':      payload.get('tally_master_id', ''),
            'company_primary_key':  payload.get('company_primary_key', ''),
            'invoice_line_ids':     line_commands,
        }, company)

        if isinstance(bill, dict):  # error dict
            return bill

        return {'tally_ref': tally_ref, 'success': True,
                'action': 'created', 'odoo_id': bill.id,
                'odoo_name': bill.name, 'move_type': 'in_invoice'}

    def _handle_out_refund(self, payload, company):
        """Customer credit note."""
        tally_ref = payload.get('tally_invoice_number') or payload.get('tally_credit_note_number')

        # Find original invoice
        original = None
        if payload.get('original_invoice_number'):
            original = request.env['account.move'].sudo().search([
                ('name', '=', payload['original_invoice_number']),
                ('company_id', '=', company.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
            ], limit=1)
        if not original and payload.get('tally_invoice_number'):
            original = request.env['account.move'].sudo().search([
                ('tally_invoice_number', '=', payload.get('tally_invoice_number')),
                ('company_id', '=', company.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
            ], limit=1)

        partner_id = original.partner_id.id if original else None
        if not partner_id:
            partner, err = self._resolve_partner(payload, company, supplier=False)
            if err:
                return err
            partner_id = partner.id

        line_commands, err = self._build_move_lines(
            payload.get('invoice_line_ids', []), company,
            account_type='income', tax_type='sale')
        if err:
            return err

        move = self._create_and_post_move({
            'move_type':            'out_refund',
            'partner_id':           partner_id,
            'company_id':           company.id,
            'invoice_date':         payload.get('invoice_date') or fields.Date.today(),
            'invoice_origin':       original.name if original else '',
            'ref':                  payload.get('reason', 'Credit Note'),
            'tally_invoice_number': tally_ref,
            'tally_master_id':      payload.get('tally_master_id', ''),
            'reversed_entry_id':    original.id if original else False,
            'invoice_line_ids':     line_commands,
        }, company)

        if isinstance(move, dict):
            return move

        return {'tally_ref': tally_ref, 'success': True,
                'action': 'created', 'odoo_id': move.id,
                'odoo_name': move.name, 'move_type': 'out_refund'}

    def _handle_in_refund(self, payload, company):
        """Vendor debit note / purchase return."""
        tally_ref = payload.get('tally_invoice_number') or payload.get('tally_debit_note_number')

        original = None
        if payload.get('original_bill_number'):
            original = request.env['account.move'].sudo().search([
                ('name', '=', payload['original_bill_number']),
                ('company_id', '=', company.id),
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
            ], limit=1)

        partner_id = original.partner_id.id if original else None
        if not partner_id:
            partner, err = self._resolve_partner(payload, company, supplier=True)
            if err:
                return err
            partner_id = partner.id

        line_commands, err = self._build_move_lines(
            payload.get('invoice_line_ids', []), company,
            account_type='expense', tax_type='purchase')
        if err:
            return err

        move = self._create_and_post_move({
            'move_type':            'in_refund',
            'partner_id':           partner_id,
            'company_id':           company.id,
            'invoice_date':         payload.get('invoice_date') or fields.Date.today(),
            'invoice_origin':       original.name if original else '',
            'ref':                  payload.get('reason', 'Debit Note'),
            'tally_invoice_number': tally_ref,
            'tally_master_id':      payload.get('tally_master_id', ''),
            'reversed_entry_id':    original.id if original else False,
            'invoice_line_ids':     line_commands,
        }, company)

        if isinstance(move, dict):
            return move

        return {'tally_ref': tally_ref, 'success': True,
                'action': 'created', 'odoo_id': move.id,
                'odoo_name': move.name, 'move_type': 'in_refund'}

    # ── Shared helpers ──────────────────────────────────────────────────────

    def _resolve_partner(self, payload, company, supplier=False):
        """Find or create a partner from payload."""
        name = (payload.get('customer_name') or payload.get('vendor_name') or '').strip()
        vat  = payload.get('vat', '')

        partner = None
        if vat:
            partner = request.env['res.partner'].sudo().search([
                ('vat', '=', vat),
                ('company_id', 'in', [company.id, False])
            ], limit=1)
        if not partner and name:
            partner = request.env['res.partner'].sudo().search([
                ('name', 'ilike', name),
                ('company_id', 'in', [company.id, False])
            ], limit=1)
        if not partner and name:
            partner = request.env['res.partner'].sudo().create({
                'name':          name,
                'vat':           self._clean_gstin(vat),
                'street':        payload.get('street', ''),
                'zip':           payload.get('zip', ''),
                'company_id':    False,
                'supplier_rank': 1 if supplier else 0,
                'customer_rank': 0 if supplier else 1,
            })
        if not partner:
            return None, {
                'success': False, 'status': 404,
                'message': f"Partner '{name}' not found and could not be created."
            }
        return partner, None

    def _build_move_lines(self, invoice_line_ids, company,
                          account_type='income', tax_type='sale'):
        """
        Build (0,0,{...}) line commands.
        account_type: 'income' for sales, 'expense' for purchases
        tax_type:     'sale'   for sales, 'purchase' for purchases
        """
        lines = []
        for child in invoice_line_ids:
            default_code = (child.get('default_code') or '').strip()
            if not default_code:
                continue

            product = request.env['product.product'].sudo().search([
                ('default_code', '=', default_code)
            ], limit=1)
            if not product:
                return None, {
                    'success': False, 'status': 404,
                    'message': f"Product '{default_code}' not found."
                }

            product = product.with_company(company)

            if account_type == 'income':
                account = (product.property_account_income_id
                           or product.categ_id.property_account_income_categ_id)
            else:
                account = (product.property_account_expense_id
                           or product.categ_id.property_account_expense_categ_id)

            if not account:
                return None, {
                    'success': False, 'status': 400,
                    'message': (f"No {account_type} account for product '{default_code}'. "
                                f"Please configure it in Odoo.")
                }

            tax_list_ids = child.get('tax_list_ids', [])
            if tax_list_ids:
                if not isinstance(tax_list_ids, list):
                    tax_list_ids = [tax_list_ids]
                resolved = []
                for tax_item in tax_list_ids:
                    if isinstance(tax_item, int):
                        resolved.append(tax_item)
                    elif isinstance(tax_item, str):
                        if tax_type == 'purchase':
                            ids, err = self._resolve_tally_tax_purchase(tax_item, company)
                        else:
                            ids, err = self._resolve_tally_tax(tax_item, company)
                        if err:
                            return None, err
                        resolved.extend(ids)
                tax_cmd = [(6, 0, resolved)] if resolved else [(5, 0, 0)]
            else:
                tax_cmd = [(5, 0, 0)]

            lines.append({
                'product_id': product.id,
                'name':       child.get('name') or product.name,
                'quantity':   child.get('quantity', 1),
                'price_unit': child.get('price_unit', 0.0),
                'account_id': account.id,
                'discount':   child.get('discount', 0.0),
                'tax_ids':    tax_cmd,
            })

        if not lines:
            return [], None
        return [(0, 0, d) for d in lines], None

    def _create_and_post_move(self, vals, company):
        """Create and post an account.move, return the record or error dict."""
        try:
            with request.env.cr.savepoint():
                env = request.env(
                    user=company.user_ids[0].id if company.user_ids else SUPERUSER_ID)
                move = env['account.move'].sudo().with_company(company).create(vals)
                move.action_post()
            return move
        except Exception as e:
            _logger.exception("_create_and_post_move error: %s", e)
            self._safe_rollback(request.env.cr)
            return {'success': False, 'status': 500, 'message': str(e)}

    def _update_move(self, move, payload, company, tax_type='sale'):
        """Reset to draft, replace lines, re-post."""
        try:
            with request.env.cr.savepoint():
                inv = move.with_company(company).with_user(SUPERUSER_ID)
                if inv.state != 'draft':
                    inv.button_draft()
                account_type = 'expense' if move.move_type in ('in_invoice','in_refund') else 'income'
                line_commands, err = self._build_move_lines(
                    payload.get('invoice_line_ids', []), company,
                    account_type=account_type, tax_type=tax_type)
                if err:
                    return err
                inv.write({
                    'invoice_origin': payload.get('invoice_origin', ''),
                    'invoice_line_ids': [(5, 0, 0)] + line_commands,
                })
                inv.action_post()
        except Exception as e:
            self._safe_rollback(request.env.cr)
            return {'success': False, 'status': 500, 'message': str(e)}
        return None

    def _create_and_validate_receipt(self, bill, payload, company):
        """
        Create a stock receipt (stock.picking) for a vendor bill and validate
        it immediately so stock moves appear in inventory history.

        Uses SUPERUSER so env.user.partner_id.id is always a valid integer.
        auth=none routes have no real user — button_validate() calls
        message_subscribe() which passes False as partner_id otherwise,
        causing 'operator does not exist: integer = boolean' SQL error.
        """
        try:
            safe_env = request.env(
                user=SUPERUSER_ID,
                context={
                    **request.env.context,
                    'allowed_company_ids': [company.id],
                    'force_company': company.id,
                }
            )

            # ── 1. Find incoming picking type ─────────────────────────────
            picking_type = safe_env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('warehouse_id.company_id', '=', company.id),
            ], limit=1)

            if not picking_type:
                return {
                    'success': False,
                    'message': (f"No incoming picking type found for company "
                                f"'{company.name}'. Please configure a warehouse.")
                }

            supplier_loc = (picking_type.default_location_src_id
                            or safe_env.ref('stock.stock_location_suppliers'))
            dest_loc     = (picking_type.default_location_dest_id
                            or safe_env.ref('stock.stock_location_stock'))

            # ── 2. Build move lines (storable products only) ──────────────
            move_lines = []
            for line in bill.invoice_line_ids.filtered(
                    lambda l: l.product_id and l.display_type == 'product'):
                product = line.product_id
                if product.type not in ('product', 'consu'):
                    continue
                move_lines.append((0, 0, {
                    'name':            product.name,
                    'product_id':      product.id,
                    'product_uom':     line.product_uom_id.id or product.uom_id.id,
                    'product_uom_qty': abs(line.quantity),
                    'location_id':     supplier_loc.id,
                    'location_dest_id': dest_loc.id,
                    'company_id':      company.id,
                }))

            if not move_lines:
                _logger.info(
                    "_create_and_validate_receipt: no storable lines in '%s'.",
                    bill.name)
                return None

            # ── 3. Create picking ─────────────────────────────────────────
            picking = safe_env['stock.picking'].create({
                'picking_type_id':  picking_type.id,
                'partner_id':       bill.partner_id.id,
                'origin':           bill.name,
                'company_id':       company.id,
                'move_ids':         move_lines,
                'location_id':      supplier_loc.id,
                'location_dest_id': dest_loc.id,
            })

            # ── 4. Confirm, assign, set done qty, validate ────────────────
            picking.action_confirm()
            picking.action_assign()

            for move in picking.move_ids:
                move.quantity = move.product_uom_qty

            # button_validate uses env.user.partner_id internally.
            # With SUPERUSER this is always a valid integer — no SQL error.
            picking.with_context(
                skip_backorder=True,
                immediate_transfer=True,
            ).button_validate()

            _logger.info(
                "✓ Receipt '%s' (id:%s) validated for bill '%s'",
                picking.name, picking.id, bill.name)

            return picking

        except Exception as e:
            _logger.exception(
                "_create_and_validate_receipt error for bill '%s': %s",
                bill.name, str(e))
            return {'success': False, 'message': str(e)}


    # ══════════════════════════════════════════════════════════════════════════
    # CANCEL / DELETE ENDPOINT  —  /web/api/cancel_vendor_bill
    #
    # Called when Tally person deletes or cancels a purchase voucher.
    # Cancels the Odoo bill AND reverses the stock receipt.
    #
    # Payload:
    # {
    #   "jsonrpc": "2.0", "method": "call",
    #   "params": {
    #     "api_token": "xxx",
    #     "tally_invoice_number": "PUR/2026/001",
    #     "reason": "Cancelled by vendor"   (optional)
    #   }
    # }
    # ══════════════════════════════════════════════════════════════════════════

    @http.route('/web/api/cancel_vendor_bill', type='json', auth='none',
                methods=['POST'], csrf=False)
    def cancel_vendor_bill(self, **params):
        """
        Cancel a vendor bill from Tally and reverse its stock receipt.
        """
        api_token = params.get('api_token')
        if not api_token:
            return {'success': False, 'message': 'API Token required', 'status': 401}

        company = request.env['res.company'].sudo().search([
            ('api_token', '=', api_token)
        ], limit=1)
        if not company:
            return {'success': False, 'message': 'Invalid API Token', 'status': 401}

        tally_ref = params.get('tally_invoice_number')
        if not tally_ref:
            return {'success': False,
                    'message': 'tally_invoice_number is required', 'status': 400}

        bill = request.env['account.move'].sudo().search([
            ('tally_invoice_number', '=', tally_ref),
            ('company_id', '=', company.id),
            ('move_type', '=', 'in_invoice'),
        ], limit=1)

        if not bill:
            return {
                'success': False,
                'message': f"Vendor bill '{tally_ref}' not found in Odoo.",
                'status': 404
            }

        if bill.state == 'cancel':
            return {
                'success': True,
                'message': f"Vendor bill '{tally_ref}' was already cancelled.",
                'status': 200
            }

        try:
            # ── Step 1: Reverse stock receipt first ───────────────────────
            old_pickings = request.env['stock.picking'].sudo().search([
                ('origin', '=', bill.name),
                ('picking_type_code', '=', 'incoming'),
                ('state', '=', 'done'),
                ('company_id', '=', company.id),
            ])

            for pick in old_pickings:
                try:
                    return_wizard = request.env['stock.return.picking'].sudo().with_context(
                        active_id=pick.id,
                        active_model='stock.picking'
                    ).create({'picking_id': pick.id})
                    result = return_wizard.create_returns()
                    return_pick = request.env['stock.picking'].sudo().browse(
                        result['res_id'])
                    for move in return_pick.move_ids:
                        move.quantity = move.product_uom_qty
                    return_pick.with_context(
                        skip_backorder=True,
                        immediate_transfer=True,
                    ).button_validate()
                    _logger.info(
                        "✓ Reversed receipt '%s' for cancelled bill '%s'",
                        pick.name, tally_ref)
                except Exception as re:
                    _logger.warning(
                        "Could not reverse receipt '%s': %s", pick.name, str(re))

            # ── Step 2: Cancel the bill ───────────────────────────────────
            if bill.state == 'posted':
                bill.button_draft()
            bill.button_cancel()

            _logger.info("✓ Vendor bill '%s' (id:%s) cancelled.", tally_ref, bill.id)

            return {
                'success': True,
                'status': 200,
                'message': f"Vendor bill '{tally_ref}' cancelled and stock reversed.",
                'odoo_id': bill.id,
                'odoo_name': bill.name,
            }

        except Exception as e:
            _logger.exception("Error cancelling vendor bill '%s': %s", tally_ref, e)
            self._safe_rollback(request.env.cr)
            return {'success': False, 'message': str(e), 'status': 500}

    def _create_and_validate_delivery(self, invoice, company):
        """
        Create a stock delivery (stock.picking, type=outgoing) for a
        customer invoice and immediately validate it so stock moves appear
        in the stock valuation layer.

        Uses SUPERUSER so env.user.partner_id is always a valid integer.
        auth=none routes have no real user — button_validate() calls
        message_subscribe() which passes False as partner_id otherwise.
        """
        try:
            safe_env = request.env(
                user=SUPERUSER_ID,
                context={
                    **request.env.context,
                    'allowed_company_ids': [company.id],
                    'force_company': company.id,
                }
            )

            # ── 1. Find outgoing picking type ─────────────────────────────
            picking_type = safe_env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
                ('warehouse_id.company_id', '=', company.id),
            ], limit=1)

            if not picking_type:
                return {
                    'success': False,
                    'message': (f"No outgoing picking type found for company "
                                f"'{company.name}'. Please configure a warehouse.")
                }

            src_loc  = (picking_type.default_location_src_id
                        or safe_env.ref('stock.stock_location_stock'))
            dest_loc = (picking_type.default_location_dest_id
                        or safe_env.ref('stock.stock_location_customers'))

            # ── 2. Build move lines from invoice lines ────────────────────
            move_lines = []
            for line in invoice.invoice_line_ids.filtered(
                    lambda l: l.product_id and l.display_type == 'product'):

                product = line.product_id

                # Only storable products affect stock
                if product.type not in ('product', 'consu'):
                    continue

                move_lines.append((0, 0, {
                    'name':             product.name,
                    'product_id':       product.id,
                    'product_uom':      line.product_uom_id.id or product.uom_id.id,
                    'product_uom_qty':  abs(line.quantity),
                    'location_id':      src_loc.id,
                    'location_dest_id': dest_loc.id,
                    'company_id':       company.id,
                }))

            if not move_lines:
                _logger.info(
                    "_create_and_validate_delivery: no storable lines in '%s'.",
                    invoice.name)
                return None

            # ── 3. Create picking ─────────────────────────────────────────
            picking = safe_env['stock.picking'].create({
                'picking_type_id':  picking_type.id,
                'partner_id':       invoice.partner_id.id,
                'origin':           invoice.name,
                'company_id':       company.id,
                'move_ids':         move_lines,
                'location_id':      src_loc.id,
                'location_dest_id': dest_loc.id,
            })

            # ── 4. Confirm, set done qty, validate ────────────────────────
            picking.action_confirm()
            picking.action_assign()

            for move in picking.move_ids:
                move.quantity = move.product_uom_qty

            picking.with_context(
                skip_backorder=True,
                immediate_transfer=True,
            ).button_validate()

            _logger.info(
                "✓ Delivery '%s' (id:%s) validated for invoice '%s'",
                picking.name, picking.id, invoice.name)

            return picking

        except Exception as e:
            _logger.exception(
                "_create_and_validate_delivery error for invoice '%s': %s",
                invoice.name, str(e))
            return {'success': False, 'message': str(e)}