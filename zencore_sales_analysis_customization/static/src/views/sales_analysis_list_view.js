import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { SalesAnalysisListRenderer } from "./sales_analysis_list_renderer";

export const SalesAnalysisListView = {
    ...listView,
    Renderer: SalesAnalysisListRenderer,
};

registry.category("views").add("sales_analysis_free_product_list", SalesAnalysisListView);

