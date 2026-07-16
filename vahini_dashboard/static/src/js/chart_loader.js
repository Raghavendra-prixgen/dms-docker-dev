/** @odoo-module **/
import { loadJS } from "@web/core/assets";

(async () => {
    if (!window.Chart) {
        try {
            await loadJS("https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js");
        } catch (e) {
            console.error("Vahini Dashboard: Failed to load Chart.js", e);
        }
    }
})();
