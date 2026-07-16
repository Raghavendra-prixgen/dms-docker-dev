/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { navDefs } from "../../js/dashboardData";

export class SideDrawer extends Component {
    static template = "vahini_dashboard.SideDrawer";
    static props = {
        activeView: String,
        onNavClick: Function,
    };

    setup() {
        this.state   = useState({ open: false });
        this.navDefs = navDefs;
    }

    toggleSidebar() { this.state.open = !this.state.open; }

    onItemClick(ev, item) {
        ev.preventDefault();
        this.props.onNavClick(item.view || item.label.toLowerCase());
    }
}
