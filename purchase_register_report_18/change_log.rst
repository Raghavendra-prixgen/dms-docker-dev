17.0.1.1 ------> 18.0.0.1 ***Anke***
==================================================
Conversion

18.0.0.1 ------> 18.0.0.2 (12/Nov/2024) ***Anke***
==================================================
Updated Views

18.0.0.2 ------> 18.0.0.3(21-11-2024) ***Anke***
================================================
Updated Sudo for company access

18.0.0.3 ------> 18.0.0.4(23-11-2024) ***Anke***
================================================
Updated Company Clause

18.0.0.4 ----> 18.0.0.5(**29/Nov/2024**)***Anke***
==================================================
company domain added

18.0.0.5 ----> 18.0.0.6(**27/Dec/2024**)***Anke***
==================================================
Bug fix

18.0.0.6 ----> 18.0.0.7(**27/Dec/2024**)***Anke***
==================================================
company domain added filter

18.0.0.7 ----> 18.0.0.8(**08/Jan/2024**)***Anke***
==================================================
Updated where clause

18.0.0.8 ----> 18.0.0.9(**08/Jan/2024**)***Anke***
==================================================
Bug Fix(analytic)

18.0.0.9 ----> 18.0.1.0(**22/Apr/2024**)***Anke***
==================================================
Bug Fix(product_categ)

18.0.1.0 ----> 18.0.1.1(**06/May/2025**)***Anke***
==================================================
Added move and move_line field in view

18.0.1.1 ----> 18.0.1.2(**09/May/2025**)***Anke***
==================================================
Bug Fix(Removed RCM,Ocean Tax from Total Tax sum)

18.0.1.2 ----> 18.0.1.3(**12/May/2025**)***$@g@r***
==================================================
added xlsx report

18.0.1.3 ----> 18.0.1.4(**12/May/2025**)***$@g@r***
==================================================
added accounting date bill ref rcm tax percent and amount grn ref field in purchase register report

18.0.1.4 ----> 18.0.1.5(**12/May/2025**)***$@g@r***
==================================================
removed account id

18.0.1.5 ----> 18.0.1.6(**12/May/2025**)***$@g@r***
==================================================
added company filter

18.0.1.8 ----> 18.0.1.9(**13/May/2025**)***$@g@r***
==================================================
added rcm split amount and tax rate

18.0.2.0 ----> 18.0.2.1(**15/May/2025**)***$@g@r***
==================================================
added rcm split amount and tax rate in tree view report

18.0.2.1 ----> 18.0.2.2(**27/Jun/2025**)***Anke***
==================================================
Bug fix(GRN Reference)

18.0.2.2 ----> 18.0.2.3(**16/Jul/2025**)***Anke***
==================================================
Added Payment Terms and Payment Date

=========================================================================
## [18.0.2.4] - 2025-11-05 ***Anke***
### ✏️ Update: Label Corrections

**Module:** "purchase_register_report_18"

#### 🔹 Changes
| File | Line | Old Text | Corrected Text |
|------|------|-----------|----------------|
| "model/purchase_register_report.py" | 43 | Product Uom | Product UoM |
| "model/purchase_register_report.py" | 76 | Bill Ageing | Bill Aging |

#### ✅ Impact
- Standardized label capitalization and corrected spelling.  
- Improved report field naming consistency.  
- No functional or performance changes.

=====================================================
[FIX] Fix Purchase Register Domain Construction Error

Version: 18.0.2.6
Previous Version: 18.0.2.5
Date: 05-Jan-2026
Author: Anke

Change Summary

Fixed runtime error caused by the use of an undefined variable date_clause in purchase register domain logic.

Refactored domain construction to use pure Odoo ORM domains instead of mixed SQL-style string conditions.

Improved partner and product category filtering logic for better accuracy and maintainability.

Standardized date filtering for accounting date and invoice date selections.

Enhanced multi-company domain handling to ensure correct company-level access.

Functional behavior preserved; stability and code quality improvements only.

Impact

Prevents runtime failures during report execution

Improves reliability of purchase register data

Cleaner and more maintainable domain construction logic

Upgrade-safe and ORM-compliant implementation

=====================================================
[FIX] Updated (-) values for refund

Version: 18.0.2.7
Previous Version: 18.0.2.6
Date: 16-Jan-2026
Author: Anke

=====================================================
[FIX] added display type product in condition and discount and rap price field addition

Version: 18.0.2.8
Previous Version: 18.0.2.7
Date: 07-Jan-2026
Author: Sagar

=====================================================
[IMP] Added Partner Ref field

Version: 18.0.2.9
Previous Version: 18.0.2.8
Date: 10-Mar-2026
Author: Anke
