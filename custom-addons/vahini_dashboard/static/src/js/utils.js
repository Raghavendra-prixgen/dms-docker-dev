/** @odoo-module **/

export function fmt(value) {
    const n = parseFloat(value);
    if (value === undefined || value === null || isNaN(n)) return "";
    const abs = Math.abs(n);
    const str = abs.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    return n < 0 ? "-" + str : str;
}


export function hex2rgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}


export function buildPageNums(total, current) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const pages = [1];
    if (current > 3) pages.push("...");
    for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
        pages.push(i);
    }
    if (current < total - 2) pages.push("...");
    pages.push(total);
    return pages;
}
