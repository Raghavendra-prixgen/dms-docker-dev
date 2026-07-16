/** @odoo-module **/
import { Dropdown }     from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { CheckBox }     from "@web/core/checkbox/checkbox";
import { registry }     from "@web/core/registry";
import { useService }   from "@web/core/utils/hooks";
import { Component }    from "@odoo/owl";

const userMenuRegistry = registry.category("user_menuitems");

export class SidebarBottom extends Component {
    static template = "SidebarBottom";
    static components = { Dropdown, DropdownItem, CheckBox };
    static props = {};

    setup() {
        const session = odoo.__session_info__ || {};
        const uid = session.uid || session.user_id || 1;
        this.source   = `${window.location.origin}/web/image?model=res.users&field=avatar_128&id=${uid}`;
        this.userName = session.name || session.username || "";
        this.dbName   = session.db || "";
        this.actionService = useService("action");
    }

    openPreferences() {
        this.actionService.doAction("base_setup.action_general_configuration");
    }
}
