/** @odoo-module **/
import { Component, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class InvoiceView extends Component {
    static template = "vahini_dashboard.InvoiceView";
    static props = {};

    setup() {
        this.actionService = useService("action");
        this.mountRef      = useRef("mount");
        this._mounted      = false;

        onMounted(async () => {
            this._mounted = true;
            try {
                await this.actionService.doAction(
                    "account.action_move_out_invoice_type",
                    {
                        clearBreadcrumbs: true,
                        onClose: () => {},
                    }
                );
            } catch(e) {
                console.error("InvoiceView:", e);
            }
        });

        onWillUnmount(() => { this._mounted = false; });
    }
}
