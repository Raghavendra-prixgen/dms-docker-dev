/** @odoo-module **/
import { NavBar }    from "@web/webclient/navbar/navbar";
import { useService } from "@web/core/utils/hooks";
import { patch }     from "@web/core/utils/patch";
import { useEnvDebugContext } from "@web/core/debug/debug_context";
import { onMounted } from "@odoo/owl";

patch(NavBar.prototype, {
    setup() {
        super.setup();
        this.debugContext   = useEnvDebugContext();
        this.companyService = useService("company");
        this.currentCompany = this.companyService.currentCompany;
        this.menuService    = useService("menu");
        this.actionService  = useService("action");

        onMounted(() => {
            document.addEventListener("click", (ev) => {
                const link = ev.target.closest("a.child_menus");
                if (!link) return;
                ev.preventDefault();
                ev.stopPropagation();
                const menuId = parseInt(link.getAttribute("data-menu"));
                if (!menuId) return;
                const menu = this.menuService.getMenu(menuId);
                if (!menu) return;

                // Use menuService.selectMenu - the correct Odoo 18 way
                this.menuService.selectMenu(menu);
            });
        });
    },
    toggleSidebar(ev) {
        ev.currentTarget.classList.toggle("visible");
        const nav = document.querySelector(".nav-wrapper-ui");
        if (nav) nav.classList.toggle("toggle-show");
    },
    BackMenuToggle(ev) {
        const parent = ev.currentTarget.parentElement;
        if (parent) parent.classList.remove("show");
    },
});
