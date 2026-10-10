# CS

**Author:** Mehedi Hasan  
**Website:** https://www.zencoreltd.com  
**Target:** Odoo 19 Enterprise (uses the standard Approvals app)

## What this module does

This module introduces a vendor-independent purchase requisition workflow connected to Odoo Approvals. A single requisition can generate multiple custom Vendor RFQs. RFQs are compared strictly within the same requisition, product line by product line.

### Core flow

Approval Request → Purchase Requisition → Multiple Vendor RFQs → Requisition-only RFQ Comparison → Product-wise Recommend / Reject / Cancel → Multiple Purchase Orders

### Business rules

- Vendor is **not required** on the requisition.
- Vendor is **required** on each Vendor RFQ.
- One requisition can have many RFQs.
- RFQs from different requisitions can never be compared together.
- Vendor quotation entry includes Unit Price, Quality (`Good`, `Average`, `Poor`) and Delivery Date.
- Delivery Date is captured per vendor RFQ line.
- Recommending one vendor for a requisition line automatically cancels the same requisition line on the other vendor RFQs.
- Purchase Orders are generated only from recommended lines and grouped by vendor.
- One requisition can therefore create multiple standard Odoo Purchase Orders.

## Installation

1. Copy `zencore_purchase_sourcing` into your Odoo custom addons path.
2. Restart Odoo.
3. Update the Apps list.
4. Install **CS**.
5. Ensure users have Purchase User or Purchase Manager access.

## Approvals integration

For Approval Type = `Requisition`, final approval automatically creates the confirmed CS requisition. Approved product lines and quantities are copied into the requisition, which keeps a direct link back to the Approval Request.

## Notes

- All RFQ prices under a requisition use the requisition comparison currency.
- Standard Odoo Purchase Orders receive the selected vendor RFQ line Delivery Date as their planned date.


## 19.0.1.0.1
- Fixed Odoo 19 installation failure caused by removed `uom.uom.category_id` / `uom.category`.
- Requisition UoM selection now follows Odoo 19 product-specific allowed UoMs.
- Draft RFQ lines may start at zero price; positive price is enforced when marking an RFQ as Received.
- Quality is now explicitly entered by the user instead of defaulting to Average.


## 19.0.1.0.2
- Fixed Odoo 19 search-view validation: search-view `<group>` no longer accepts legacy `expand` / `string` attributes.
- Updated both Requisition and Vendor RFQ search views to Odoo 19-compatible `<group name="group_by">`.

## v1.0.6
- Purchase Requisitions are approval-controlled: direct UI creation and Reset to Draft are disabled.
- For Approval Type = Requisition, quantities can be adjusted before final approval.
- Quantity changes on approval product lines are posted to the Approval Request chatter for audit history.
- After submission, product/unit/description are locked; only quantity can change until final approval.
- Final approval creates the confirmed CS requisition snapshot; approval product lines are then locked.


## v1.0.7
- Added a persistent RFQ Comparison record per requisition.
- Added a Requisition smart button to reopen the saved comparison record.
- Added line-by-line Remarks in the comparison, one remark for each product/vendor quotation row.
- Recommendation/Reject/Cancel/Reset actions are available directly on saved comparison lines.
- Comparison remarks and decisions are posted to the comparison chatter for audit history.


## v1.0.8
- Added a professional A4 landscape PDF **Comparison Sheet** generated from the Requisition.
- The report becomes available after every requisition product has one recommended vendor.
- The report title/download filename includes the requisition number: `Comparison Sheet - REQ/...`.
- Includes requisition/approval metadata, comparison metadata, product-wise vendor offers, Unit Price, Quality, Delivery Date, Decision and line Remarks.
- Recommended quotation rows are visually highlighted for quick review.
- Added Prepared By / Checked By / Procurement Review / Approved By sign-off section.
- RFQ Comparison status now becomes `Completed` when all requisition products have a recommendation, before Purchase Order generation.


## 19.0.1.0.9
- Simplified Comparison Sheet footer note.
- Removed comparison guidance text from the report.
- Recommended Vendor guidance is now shown as a compact note below the comparison table.

### 19.0.1.0.10
- Redesigned Comparison Sheet with a presales-ready executive visual style.
- Replaced bright status colors with a restrained navy/slate/teal palette.
- Improved product section hierarchy, column widths, metadata, whitespace, signature area, and footer.
- Recommended quotation lines use a subtle corporate highlight instead of a bright green fill.
