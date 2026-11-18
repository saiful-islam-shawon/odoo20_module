import { ListRenderer } from "@web/views/list/list_renderer";
import { formatFloat } from "@web/core/utils/numbers";
import { formatMonetary } from "@web/views/fields/formatters";

const TARGET_GROUP_FIELDS = ["partner_id", "product_tmpl_id", "product_id"];

export class SalesAnalysisListRenderer extends ListRenderer {
    static rowsTemplate = "zencore_sales_analysis_customization.ListRenderer.Rows";

    isTargetGroup(groupId) {
        if (!this.props.list.isGrouped) {
            return false;
        }
        if (groupId && this.props.list.groups) {
            const group = this.props.list.groups.find((g) => g.id === groupId);
            if (group && group.groupByField) {
                return TARGET_GROUP_FIELDS.includes(group.groupByField.name);
            }
        }
        return Boolean(
            this.props.list.groupByField &&
            TARGET_GROUP_FIELDS.includes(this.props.list.groupByField.name)
        );
    }

    isCustomerGroup(groupId) {
        return this.isTargetGroup(groupId);
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

    getTotalFreeAmount(list) {
        return this.getFreeRecords(list).reduce(
            (acc, r) => acc + ((r.data.product_uom_qty || 0) * (r.data.price_unit || 0)),
            0
        );
    }

    formatFreeQty(qty) {
        return formatFloat(qty, { digits: [16, 2] });
    }

    formatFreeAmount(amount, list) {
        const currencyId = list?.records?.[0]?.data?.currency_id?.[0] || this.env.company?.currency_id;
        return formatMonetary(amount, { currencyId });
    }

    formatGroupAggregate(group, column) {
        if (
            group.groupByField &&
            TARGET_GROUP_FIELDS.includes(group.groupByField.name) &&
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
