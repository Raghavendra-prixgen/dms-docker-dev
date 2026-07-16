/** @odoo-module **/

import { Component } from "@odoo/owl";
import { fmt, hex2rgba } from "../../js/utils";

export class SnapMetrics extends Component {
    static template = "vahini_dashboard.SnapMetrics";
    static props = {
        metrics: Array,
    };

    iconBoxStyle(m) {
        return `background:${hex2rgba(m.color, 0.12)};color:${m.color}`;
    }

    cardStyle(m) {
        return `--kpi-color:${m.color}`;
    }

    fmtValue(v) {
        return fmt(v);
    }
}
