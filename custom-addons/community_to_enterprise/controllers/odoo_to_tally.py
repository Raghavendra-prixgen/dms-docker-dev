from odoo import http, fields
from odoo.http import request
import requests
import json
import logging

_logger = logging.getLogger(__name__)

class ProductPushToFastAPI(http.Controller):
    
    @http.route('/web/api/push_product', type='json', auth='none', methods=['POST'], csrf=False)
    def push_product_to_fastapi(self, **kw):
        """
        Push product master data from Odoo to FastAPI middleware
        """
        try:
            # 1. AUTHENTICATE
            api_token = kw.get('api_token')
            if not api_token:
                return {
                    'success': False,
                    'status': 401,
                    'response': 'API token is required'
                }
            
            company = request.env['res.company'].sudo().search([
                ('api_token', '=', api_token)
            ], limit=1)
            
            if not company:
                return {
                    'success': False,
                    'status': 401,
                    'response': 'Invalid API token'
                }
            
            # 2. VALIDATE COMPANY (optional)
            company_primary_key = kw.get('company_primary_key')
            if company_primary_key and hasattr(company, 'company_primary_key'):
                if company.company_primary_key != company_primary_key:
                    return {
                        'success': False,
                        'status': 400,
                        'response': 'Company primary key mismatch'
                    }
            
            # 3. GET PRODUCT
            product_code = kw.get('product_code')
            if not product_code:
                return {
                    'success': False,
                    'status': 400,
                    'response': 'Product code is required'
                }
            
            product = request.env['product.product'].sudo().search([
                ('default_code', '=', product_code),
                '|',
                ('company_id', '=', company.id),
                ('company_id', '=', False)
            ], limit=1)
            
            if not product:
                return {
                    'success': False,
                    'status': 404,
                    'response': f'Product not found: {product_code}'
                }
            
            # 4. PREPARE PRODUCT DATA
            product_data = self._prepare_product_data(product, company)
            
            # 5. GET FASTAPI CONFIG
            fastapi_url = kw.get('fastapi_url')
            if not fastapi_url:
                fastapi_url = request.env['ir.config_parameter'].sudo().get_param(
                    'fastapi.product_sync_url',
                    'http://localhost:8003/product'
                )
            
            # 6. GET FASTAPI TOKEN
            fastapi_token = kw.get('fastapi_token')
            if not fastapi_token:
                fastapi_token = request.env['ir.config_parameter'].sudo().get_param(
                    'fastapi.api_token',
                    api_token  # Fallback to using same token
                )
            
            # 7. PUSH TO FASTAPI
            try:
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {fastapi_token}'
                }
                
                _logger.info(f"Pushing to FastAPI: {fastapi_url}")
                _logger.info(f"Using token: Bearer {fastapi_token[:10]}...")
                _logger.info(f"Product: {product.name} ({product_code})")
                
                response = requests.post(
                    fastapi_url,
                    json=product_data,
                    headers=headers,
                    timeout=10
                )
                
                _logger.info(f"FastAPI response status: {response.status_code}")
                _logger.info(f"FastAPI response: {response.text[:200]}")
                
                if response.status_code == 200:
                    # Update sync status - FIXED DATETIME
                    if hasattr(product, 'last_tally_sync_date'):
                        product.sudo().write({
                            'last_tally_sync_date': fields.Datetime.now(),  # FIXED
                            'tally_sync_status': 'synced'
                        })
                    
                    return {
                        'success': True,
                        'status': 200,
                        'message': 'Product pushed to FastAPI successfully',
                        'product_code': product_code,
                        'product_name': product.name,
                        'fastapi_response': response.json() if response.text else {}
                    }
                else:
                    _logger.error(f"FastAPI error: {response.text}")
                    
                    if hasattr(product, 'tally_sync_status'):
                        product.sudo().write({'tally_sync_status': 'failed'})
                    
                    return {
                        'success': False,
                        'status': response.status_code,
                        'response': f'FastAPI returned error: {response.text}'
                    }
                    
            except requests.exceptions.Timeout:
                _logger.error(f"Timeout connecting to FastAPI: {fastapi_url}")
                return {
                    'success': False,
                    'status': 408,
                    'response': 'Request timeout - FastAPI not responding'
                }
                
            except requests.exceptions.ConnectionError as e:
                _logger.error(f"Connection error to FastAPI: {fastapi_url} - {str(e)}")
                return {
                    'success': False,
                    'status': 503,
                    'response': f'Cannot connect to FastAPI - Service unavailable: {str(e)}'
                }
                
            except Exception as e:
                _logger.error(f"Error pushing to FastAPI: {str(e)}", exc_info=True)
                return {
                    'success': False,
                    'status': 500,
                    'response': f'Error: {str(e)}'
                }
                
        except Exception as e:
            _logger.error(f"Error in push_product_to_fastapi: {str(e)}", exc_info=True)
            return {
                'success': False,
                'status': 500,
                'response': f'Internal error: {str(e)}'
            }

    @http.route('/web/api/push_products_bulk', type='json', auth='none', methods=['POST'], csrf=False)
    def push_products_bulk_to_fastapi(self, **kw):
        """
        Push multiple products to FastAPI in bulk
        """
        try:
            api_token = kw.get('api_token')
            if not api_token:
                return {
                    'success': False,
                    'status': 401,
                    'response': 'API token is required'
                }
            
            company = request.env['res.company'].sudo().search([
                ('api_token', '=', api_token)
            ], limit=1)
            
            if not company:
                return {
                    'success': False,
                    'status': 401,
                    'response': 'Invalid API token'
                }
            
            company_primary_key = kw.get('company_primary_key')
            if company_primary_key and hasattr(company, 'company_primary_key'):
                if company.company_primary_key != company_primary_key:
                    return {
                        'success': False,
                        'status': 400,
                        'response': 'Company primary key is not matched'
                    }
            
            product_codes = kw.get('product_codes', [])
            if not product_codes:
                return {
                    'success': False,
                    'status': 400,
                    'response': 'Product codes list is required'
                }
            
            fastapi_url = kw.get('fastapi_url')
            if not fastapi_url:
                fastapi_url = request.env['ir.config_parameter'].sudo().get_param(
                    'fastapi.product_sync_url',
                    'http://localhost:8003/product'
                )
            
            # Get FastAPI token
            fastapi_token = kw.get('fastapi_token')
            if not fastapi_token:
                fastapi_token = request.env['ir.config_parameter'].sudo().get_param(
                    'fastapi.api_token',
                    api_token
                )
            
            success_count = 0
            failed_count = 0
            results = []
            
            for product_code in product_codes:
                try:
                    # Find product
                    product = request.env['product.product'].sudo().search([
                        ('default_code', '=', product_code),
                        '|',
                        ('company_id', '=', company.id),
                        ('company_id', '=', False)
                    ], limit=1)
                    
                    if not product:
                        failed_count += 1
                        results.append({
                            'product_code': product_code,
                            'status': 'failed',
                            'message': 'Product not found'
                        })
                        continue
                    
                    # Prepare data
                    product_data = self._prepare_product_data(product, company)
                    
                    # Push to FastAPI
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {fastapi_token}'  # FIXED
                    }
                    
                    response = requests.post(
                        fastapi_url,
                        json=product_data,
                        headers=headers,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        success_count += 1
                        if hasattr(product, 'last_tally_sync_date'):
                            product.sudo().write({
                                'last_tally_sync_date': fields.Datetime.now(),  # FIXED
                                'tally_sync_status': 'synced'
                            })
                        results.append({
                            'product_code': product_code,
                            'product_name': product.name,
                            'status': 'success',
                            'message': 'Synced successfully'
                        })
                    else:
                        failed_count += 1
                        if hasattr(product, 'tally_sync_status'):
                            product.sudo().write({'tally_sync_status': 'failed'})
                        results.append({
                            'product_code': product_code,
                            'status': 'failed',
                            'message': f'FastAPI error: {response.text}'
                        })
                        
                except Exception as e:
                    failed_count += 1
                    results.append({
                        'product_code': product_code,
                        'status': 'failed',
                        'message': str(e)
                    })
            
            return {
                'success': True,
                'status': 200,
                'message': f'Bulk push completed. Success: {success_count}, Failed: {failed_count}',
                'total': len(product_codes),
                'success_count': success_count,
                'failed_count': failed_count,
                'results': results
            }
            
        except Exception as e:
            _logger.error(f"Error in push_products_bulk_to_fastapi: {str(e)}")
            return {
                'success': False,
                'status': 500,
                'response': f'Internal error: {str(e)}'
            }
    
    def _prepare_product_data(self, product, company):
        """Prepare product data for FastAPI"""
        
        # Get taxes
        tax_list = []
        if product.taxes_id:
            tax_list = [
                {
                    'id': tax.id,
                    'name': tax.name,
                    'amount': tax.amount,
                    'type': tax.type_tax_use
                }
                for tax in product.taxes_id
            ]
        
        # Basic product data
        product_data = {
            # Basic Info
            'name': product.name,
            'default_code': product.default_code or '',
            'barcode': product.barcode or '',
            
            # Type
            'type': product.type,
            
            # Category
            'category': product.categ_id.name if product.categ_id else '',
            'category_name': product.categ_id.name if product.categ_id else 'Primary',
            
            # Pricing
            'list_price': float(product.list_price),
            'standard_price': float(product.standard_price),
            
            # UOM
            'uom_name': product.uom_id.name if product.uom_id else 'Nos',
            'uom_po_name': product.uom_po_id.name if product.uom_po_id else '',
            
            # Taxes
            'taxes': tax_list,
            'gst_rate': tax_list[0]['amount'] if tax_list else 0,
            
            # Inventory
            'qty_available': float(product.qty_available),
            
            # HSN Code
            'hsn_code': product.l10n_in_hsn_code if hasattr(product, 'l10n_in_hsn_code') else '',
            
            # Flags
            'active': product.active,
            'sale_ok': product.sale_ok,
            'purchase_ok': product.purchase_ok,
            
            # Company
            'company_id': company.id,
            'company_name': company.name,
            'company_primary_key': company.company_primary_key if hasattr(company, 'company_primary_key') else '',
            
            # Odoo Reference
            'odoo_product_id': product.id,
            'odoo_create_date': product.create_date.isoformat() if product.create_date else None,
            'odoo_write_date': product.write_date.isoformat() if product.write_date else None,
        }
        
        return product_data
    
    def _get_category_path(self, category):
        """Get full category path"""
        if not category:
            return ''
        
        path = [category.name]
        parent = category.parent_id
        
        while parent:
            path.insert(0, parent.name)
            parent = parent.parent_id
        
        return ' / '.join(path)    

    @http.route('/web/api/test_fastapi_connection', type='json', auth='none', methods=['POST'], csrf=False)
    def test_fastapi_connection(self, **kw):
        """Test connection to FastAPI"""
        try:
            # Authenticate
            api_token = kw.get('api_token')
            if not api_token:
                return {
                    'success': False,
                    'status': 401,
                    'response': 'API token is required'
                }
            
            company = request.env['res.company'].sudo().search([
                ('api_token', '=', api_token)
            ], limit=1)
            
            if not company:
                return {
                    'success': False,
                    'status': 401,
                    'response': 'Invalid API token'
                }
            
            # Get FastAPI URL
            fastapi_url = kw.get('fastapi_url')
            if not fastapi_url:
                fastapi_url = request.env['ir.config_parameter'].sudo().get_param(
                    'fastapi.product_sync_url',
                    'http://localhost:8003'
                )
            
            # Test connection to root endpoint
            try:
                response = requests.get(f"{fastapi_url.rstrip('/product')}/", timeout=5)
                
                if response.status_code == 200:
                    return {
                        'success': True,
                        'status': 200,
                        'message': 'FastAPI connection successful',
                        'fastapi_url': fastapi_url,
                        'fastapi_response': response.json() if response.text else {}
                    }
                else:
                    return {
                        'success': False,
                        'status': response.status_code,
                        'response': f'FastAPI returned status {response.status_code}'
                    }
                    
            except requests.exceptions.Timeout:
                return {
                    'success': False,
                    'status': 408,
                    'response': 'Connection timeout - FastAPI not responding'
                }
                
            except requests.exceptions.ConnectionError:
                return {
                    'success': False,
                    'status': 503,
                    'response': 'Cannot connect to FastAPI - Service unavailable'
                }
                
        except Exception as e:
            return {
                'success': False,
                'status': 500,
                'response': f'Error: {str(e)}'
            }