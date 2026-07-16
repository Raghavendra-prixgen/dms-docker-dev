/** @odoo-module **/

// ── Navigation definitions ────────────────────────────────────────────────────
// All chart/table/metric data is loaded dynamically from the Odoo backend.
// Only navDefs lives here as it is purely UI configuration.

export const navDefs = [
    { icon: "layout-dashboard", label: "Dashboard",      view: "dashboard"      },
    { icon: "calendar-days",    label: "Day View",        view: "dayview"        },
    { icon: "shopping-cart",    label: "Purchase View",   view: "purchaseview"   },
    { icon: "globe",            label: "Map View",        view: "mapview"        },
    { icon: "wallet",           label: "Payment",         view: "payment"        },
    { icon: "check-square",     label: "Follow-Up",       view: "followup"       },
    { icon: "bar-chart",        label: "Item View",       view: "itemview"       },
    { icon: "trending-up",      label: "GP View",         view: "gpview"         },
    { icon: "line-chart",       label: "Trend View",      view: "trendview"      },
    { icon: "zap",              label: "Invoices",        view: "invoices"       },
    { separator: true },
    { icon: "megaphone",        label: "Announcements",   view: "announcements"  },
    { icon: "database",         label: "Item Master",     view: "itemmaster"     },
];
