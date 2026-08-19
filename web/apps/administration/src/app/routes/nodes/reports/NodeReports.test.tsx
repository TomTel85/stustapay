import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";

const mockGenerateRevenueReport = jest.fn();
const mockGenerateAccountingReport = jest.fn();
const mockToastError = jest.fn();

jest.mock("@/api", () => ({
  useGenerateRevenueReportMutation: () => [mockGenerateRevenueReport, { isLoading: false }],
  useGenerateAccountingReportMutation: () => [mockGenerateAccountingReport, { isLoading: false }],
}));

jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({
    currentNode: {
      id: 7,
      name: "Agenda & Bar",
      event: {},
      event_node_id: 7,
    },
  }),
  useCurrentEventSettings: () => ({ eventSettings: { bon_title: "Test Festival" } }),
  useCurrentUserHasPrivilege: (privilege: string) =>
    privilege === "node_administration" || privilege === "view_node_stats",
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock("react-toastify", () => ({
  toast: { error: (...args: unknown[]) => mockToastError(...args) },
}));

import { NodeReports } from "./NodeReports";

describe("NodeReports", () => {
  beforeEach(() => {
    mockGenerateRevenueReport.mockReset();
    mockGenerateAccountingReport.mockReset();
    mockToastError.mockReset();
  });

  test("offers revenue and financial reports and downloads both PDFs", async () => {
    const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const revokeObjectURL = jest.fn();
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    mockGenerateRevenueReport.mockReturnValue({ unwrap: jest.fn().mockResolvedValue("blob:revenue") });
    mockGenerateAccountingReport.mockReturnValue({ unwrap: jest.fn().mockResolvedValue("blob:accounting") });

    render(<NodeReports />);

    fireEvent.click(screen.getByRole("button", { name: "reports.downloadRevenue" }));
    fireEvent.click(screen.getByRole("button", { name: "reports.downloadAccounting" }));

    await waitFor(() => expect(click).toHaveBeenCalledTimes(2));
    expect(mockGenerateRevenueReport).toHaveBeenCalledWith({ nodeId: 7 });
    expect(mockGenerateAccountingReport).toHaveBeenCalledWith({ nodeId: 7 });
    expect(click.mock.instances[0].download).toMatch(/^umsatzbericht_test-festival_agenda-bar_/);
    expect(click.mock.instances[1].download).toMatch(/^finanzbericht_test-festival_agenda-bar_/);
    await waitFor(() => {
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:revenue");
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:accounting");
    });
    click.mockRestore();
  });
});
