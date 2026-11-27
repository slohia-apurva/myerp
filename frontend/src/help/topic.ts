/** Which manual chapter goes with the screen that is open. Its own small file so
 * the top menu's Help link does not pull the whole manual (249 KB) into the first
 * download; the Help screen itself comes when it is opened (2026-11-25). */
/** The manual chapter for the screen at this hash, for the Help link. */
export function helpTopicFor(hash: string): string {
  const [page, id, sub] = hash.replace(/^#\/?/, "").split("?")[0].split("/");
  if (page === "batches" && sub === "trace") return "batch-trace";
  if (page === "users" || page === "roles" || page === "credit-terms" || page === "price-lists" || page === "terms" || page === "mail-templates" || page === "units" || page === "item-groups" || page === "brands" || page === "sales-people" || page === "batches" || page === "items" || page === "boms" || page === "hsn" || page === "reset" || page === "bill-reading" || page === "migration" || page === "central")
    return page;
  if (page === "request-addition") return "hsn";
  if (page === "bins") return "goods-receipts";
  if (page === "countries" || page === "pin-codes") return "places";
  if (page !== "companies") return "start";
  if (!id) return "companies";
  if (sub === "ledgers") return "ledgers";
  if (sub === "groups") return "ledger-groups";
  if (sub === "shipments") return "shipments";
  if (sub === "purchase-orders") return "purchase-orders";
  if (sub === "stock-check") return "stock-check";
  if (sub === "stock-transfers") return "stock-transfers";
  if (sub === "stock-receipts" || sub === "stock-deliveries") return "customer-stock";
  if (sub === "own-use") return "own-use";
  if (sub === "manufacturing-orders") return "manufacturing-orders";
  if (sub === "sales-orders") return "sales-orders";
  if (sub === "pick-lists") return "pick-lists";
  if (sub === "scan-picking") return "scan-picking";
  if (sub === "delivery-notes") return "delivery-notes";
  if (sub === "sales-invoices") return "sales-invoices";
  if (sub === "credit-notes") return "credit-notes";
  if (sub === "goods-receipts") return "goods-receipts";
  if (sub === "purchase-invoices") return "purchase-invoices";
  if (sub === "purchase-returns") return "purchase-returns";
  if (sub === "debit-notes") return "debit-notes";
  if (sub === "tds-check" || sub === "tds-adjustments") return "tds-check";
  if (sub === "couriers") return "transporters";
  if (sub === "insurance") return "insurance-policies";
  if (sub === "years") return "fiscal-years";
  if (sub === "warehouses") return "warehouses";
  if (sub === "stock-summary" || sub === "stock-ledger") return "stock-reports";
  if (sub === "trial-balance" || sub === "ledger-statement") return "accounts-reports";
  if (sub === "pending-purchase-orders" || sub === "procurement-tracker") return "purchase-reports";
  if (sub === "numbering") return "numbering";
  if (sub === "branches" || sub === "certificates" || sub === "modules") return sub;
  return "companies";
}
