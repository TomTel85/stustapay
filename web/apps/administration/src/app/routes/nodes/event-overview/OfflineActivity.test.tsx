import * as React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";

const mockUseOfflineReportQuery = jest.fn();
const mockUseOfflineDevicesQuery = jest.fn();
const mockOpenModal = jest.fn();

jest.mock("@/api", () => ({
  useOfflineReportQuery: (...args: unknown[]) => mockUseOfflineReportQuery(...args),
  useOfflineDevicesQuery: (...args: unknown[]) => mockUseOfflineDevicesQuery(...args),
  useDismissOfflineMutation: () => [jest.fn()],
}));

jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({ currentNode: { id: 5 } }),
  useCurrencyFormatter: () => (value: number) => `€${value.toFixed(2)}`,
}));

jest.mock("@stustapay/modal-provider", () => ({ useOpenModal: () => mockOpenModal }));
jest.mock("react-toastify", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => {
      const labels: Record<string, string> = {
        "settings.offline.activityTitle": "Offline activity",
        "settings.offline.deviceStatus": "Offline-capable tills",
        "settings.offline.importedSales": "Reported sales",
        "settings.offline.retryRequired": "Automatic reconciliation pending",
        "settings.offline.clarification": "Clarification required",
        "settings.offline.customerTagUid": `Tag UID: ${values?.uid}`,
        "settings.offline.customerAccount": `Account: ${values?.account}`,
        "settings.offline.amount": "Amount",
        "settings.offline.customer": "Customer",
        "settings.offline.buttons": "Sale buttons",
        "settings.offline.saleButton": `Button ${values?.id}`,
        "settings.offline.salePosition": `${values?.name} × ${values?.quantity} @ ${values?.price}`,
        "settings.offline.retryAttempts": `Automatic reconciliation attempts: ${values?.count}`,
        "settings.offline.lastRetryAt": `Last attempt: ${values?.time}`,
        "settings.offline.order": "Order",
        "settings.offline.status": "Status",
        "settings.offline.till": "Till",
        "settings.offline.recordedAt": "Recorded at",
        "settings.offline.receivedAt": "Received at",
        "settings.offline.balanceAfter": "Balance after",
        "settings.offline.noActivity": "No activity",
        "settings.offline.noDevices": "No devices",
        "settings.offline.dismissClarification": "Close clarification",
      };
      return labels[key] ?? key;
    },
  }),
}));

const entries = [
  {
    uuid: "pending-sale",
    snapshot_id: "snapshot-1",
    terminal_id: 1,
    till_id: 2,
    user_id: 3,
    recorded_at: "2026-10-09T10:00:00Z",
    received_at: "2026-10-09T10:01:00Z",
    status: "retry_required",
    amount_cents: 1234,
    customer_tag_uid: 98765,
    customer_account_id: 42,
    attempt_count: 3,
    last_attempt_at: "2026-10-09T10:02:00Z",
    line_items: [{ product: { name: "Historic Lager" }, quantity: 2, product_price: 5 }],
    buttons: [{ till_button_id: 10, quantity: 1, price: null }],
  },
  {
    uuid: "clarification-sale",
    snapshot_id: "snapshot-1",
    terminal_id: 1,
    till_id: 2,
    user_id: 3,
    recorded_at: "2026-10-09T10:00:00Z",
    received_at: "2026-10-09T10:01:00Z",
    status: "clarification_required",
    amount_cents: 250,
    customer_tag_uid: 12345,
    customer_account_id: null,
    buttons: [{ till_button_id: 11, quantity: null, price: 2.5 }],
  },
];

const { OfflineActivity } = require("./OfflineActivity");

describe("OfflineActivity", () => {
  beforeEach(() => {
    mockUseOfflineReportQuery.mockReset().mockReturnValue({ data: entries, isLoading: false, isError: false });
    mockUseOfflineDevicesQuery.mockReset().mockReturnValue({ data: [], isLoading: false, isError: false });
    mockOpenModal.mockReset();
  });

  test("shows reconciliation details and only offers manual close for clarification", () => {
    render(<OfflineActivity />);
    fireEvent.click(screen.getByRole("button", { name: "Reported sales" }));

    expect(screen.getByText("Automatic reconciliation pending")).toBeTruthy();
    expect(screen.getByText("Clarification required")).toBeTruthy();

    const pendingRow = screen.getByText("pending-sale").closest("tr");
    expect(pendingRow).not.toBeNull();
    const pending = within(pendingRow as HTMLElement);
    expect(pending.getByText("€12.34")).toBeTruthy();
    expect(pending.getByText("Tag UID: 98765")).toBeTruthy();
    expect(pending.getByText("Account: 42")).toBeTruthy();
    expect(pending.getByText("Historic Lager × 2 @ €5.00")).toBeTruthy();
    expect(pending.queryByText("Button 10 × 1")).toBeNull();
    expect(pending.getByText("Automatic reconciliation attempts: 3")).toBeTruthy();
    expect(pending.getByText(/^Last attempt:/)).toBeTruthy();
    expect(pending.queryByRole("button", { name: "Close clarification" })).toBeNull();

    const clarificationRow = screen.getByText("clarification-sale").closest("tr");
    expect(clarificationRow).not.toBeNull();
    const clarification = within(clarificationRow as HTMLElement);
    expect(clarification.getByText("€2.50")).toBeTruthy();
    expect(clarification.getByText("Tag UID: 12345")).toBeTruthy();
    expect(clarification.getByText("Account: —")).toBeTruthy();
    expect(clarification.getByText("Button 11 (€2.50)")).toBeTruthy();
    fireEvent.click(clarification.getByRole("button", { name: "Close clarification" }));
    expect(mockOpenModal).toHaveBeenCalledTimes(1);
  });

  test("polls the report and device status every ten seconds while focused", () => {
    render(<OfflineActivity />);

    const options = { pollingInterval: 10_000, skipPollingIfUnfocused: true };
    expect(mockUseOfflineReportQuery).toHaveBeenCalledWith({ nodeId: 5 }, options);
    expect(mockUseOfflineDevicesQuery).toHaveBeenCalledWith({ nodeId: 5 }, options);
  });
});
