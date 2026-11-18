import { ListRenderer } from "@web/views/list/list_renderer";
import { formatFloat } from "@web/core/utils/numbers";

export class SalesAnalysisListRenderer extends ListRenderer {
    static rowsTemplate = "zencore_sales_analysis_customization.ListRenderer.Rows";

    isCustomerGroup(groupId) {
        if (!this.props.list.isGrouped) {
            return false;
        }
        if (groupId && this.props.list.groups) {
            const group = this.props.list.groups.find((g) => g.id === groupId);
            if (group && group.groupByField) {
                return group.groupByField.name === "partner_id";
            }
        }
        return Boolean(
            this.props.list.groupByField &&
            this.props.list.groupByField.name === "partner_id"
        );
    }

    getSoldRecords(list) {
        return (list?.records || []).filter((r) => !r.data.is_free_product);
    }

    getFreeRecords(list) {
        return (list?.records || []).filter((r) => r.data.is_free_product);
    }

    hasFreeProducts(list) {
        return this.getFreeRecords(list).length > 0;
    }

    getTotalFreeQty(list) {
        return this.getFreeRecords(list).reduce(
            (acc, r) => acc + (r.data.product_uom_qty || 0),
            0
        );
    }

    formatFreeQty(qty) {
        return formatFloat(qty, { digits: [16, 2] });
    }

    formatGroupAggregate(group, column) {
        if (
            group.groupByField &&
            group.groupByField.name === "partner_id" &&
            (column.name === "product_uom_qty" || column.name === "price_total" || column.name === "price_subtotal")
        ) {
            if (group.list && group.list.records && group.list.records.length > 0) {
                const soldRecords = this.getSoldRecords(group.list);
                const sumVal = soldRecords.reduce(
                    (acc, r) => acc + (r.data[column.name] || 0),
                    0
                );
                if (column.name === "product_uom_qty") {
                    return { value: this.formatFreeQty(sumVal) };
                }
            }
        }
        return super.formatGroupAggregate(group, column);
    }
}

