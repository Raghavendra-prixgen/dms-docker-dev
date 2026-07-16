/** @odoo-module **/
import { rpc }           from "@web/core/network/rpc";
import { useService }    from "@web/core/utils/hooks";
import { WebClient }     from "@web/webclient/webclient";
import { patch }         from "@web/core/utils/patch";
import { useRef }        from "@odoo/owl";
import { SidebarBottom } from "./SidebarBottom";

patch(WebClient.prototype, {
    setup() {
        super.setup();
        this.root           = useRef("root");
        this.companyService = useService("company");
        this.menuService    = useService("menu");
        this.currentCompany = this.companyService.currentCompany;
        this.fetch_menu_data();
    },
    toggleSidebar(ev) {
        ev.currentTarget.classList.toggle("visible");
        const nav = document.querySelector(".nav-wrapper-ui");
        if (nav) nav.classList.toggle("toggle-show");
    },
    fetch_menu_data() {
        const menu_data = this.menuService.getApps();
        const self = this;
        rpc("/get/menu_data", { menu_ids: menu_data.map(a => a.id) })
            .then(function(rec) {
                menu_data.forEach(function(menu) {
                    if (!self.root.el) return;
                    const el = self.root.el.querySelector(
                        '.primary-nav a.main_link[data-menu="' + menu.id + '"]'
                    );
                    if (!el) return;
                    const icon_wrap = el.querySelector(".app_icon");
                    if (!icon_wrap) return;
                    const pr = rec[menu.id] && rec[menu.id][0];
                    if (!pr) return;
                    menu.id = pr.id;
                    let img = "";
                    if (pr.icon_class_name) {
                        img = "<span class='ri " + pr.icon_class_name + "'></span>";
                    } else if (pr.icon_img) {
                        img = "<img class='img img-fluid' src='/web/image/ir.ui.menu/" + pr.id + "/icon_img'/>";
                    } else if (pr.web_icon) {
                        const d = pr.web_icon.split("/icon.");
                        img = d[1] === "svg"
                            ? "<img class='img img-fluid' src='" + pr.web_icon.replace(",", "/") + "'/>"
                            : "<img class='img img-fluid' src='data:image/" + d[1] + ";base64," + pr.web_icon_data + "'/>";
                    } else {
                        img = "<img class='img img-fluid' src='/web/binary/company_logo'/>";
                    }
                    icon_wrap.innerHTML = img;
                });
            })
            .catch(function() {});
    },
    BackMenuToggle(ev) {
        const parent = ev.currentTarget.parentElement;
        if (parent) parent.classList.remove("show");
    },
    get currentMenuId() {
        return new URLSearchParams(window.location.hash.substring(1)).get("menu_id");
    }
});

patch(WebClient, {
    components: { ...WebClient.components, SidebarBottom },
});
