def migrate(cr, version):
    """Backfill the new Delivery Date from legacy Delivery Time (Days).

    Versions <= 19.0.1.0.2 stored a day count.  On upgrade, preserve existing
    test/production RFQs by using Quotation Date + legacy day count.
    New RFQs use Delivery Date directly.
    """
    cr.execute(
        """
        UPDATE zc_vendor_rfq_line AS line
           SET delivery_date = rfq.quotation_date + line.delivery_time
          FROM zc_vendor_rfq AS rfq
         WHERE line.rfq_id = rfq.id
           AND line.delivery_date IS NULL
           AND line.delivery_time IS NOT NULL
           AND line.delivery_time >= 0
           AND rfq.quotation_date IS NOT NULL
        """
    )
