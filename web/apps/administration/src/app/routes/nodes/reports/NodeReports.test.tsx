import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";

import { NodeReports } from "./NodeReports";

const mockGenerateRevenueReport = jest.fn();
const mockGenerateAccountingReport = jest.fn();
const mockToastError = jest.fn();
let mockDailyEndTime: string | undefined = "06:00:00";

jest.mock("@/api", () => ({
  useGenerateRevenueReportMutation: () => [mockGenerateRevenueReport, { isLoading: false }],
  useGenerateAccountingReportMutation: () => [mockGenerateAccountingReport, { isLoading: false }],
  useGetAvailableDatesQuery: () => ({ data: ["2026-01-03", "2026-01-04"] }),
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
  useCurrentEventSettings: () => ({
    eventSettings: { bon_title: "Test Festival", daily_end_time: mockDailyEndTime },
  }),
  useCurrentUserHasPrivilege: (privilege: string) =>
    privilege === "node_administration" || privilege === "view_node_stats",
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

jest.mock("react-toastify", () => ({
  toast: { error: (...args: unknown[]) => mockToastError(...args) },
}));

describe("NodeReports", () => {
  beforeEach(() => {
    mockGenerateRevenueReport.mockReset();
    mockGenerateAccountingReport.mockReset();
    mockToastError.mockReset();
    mockDailyEndTime = "06:00:00";
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
    expect(mockGenerateRevenueReport).toHaveBeenCalledWith({
      nodeId: 7,
      selectedDates: undefined,
      dayMode: "calendar_day",
    });
    expect(mockGenerateAccountingReport).toHaveBeenCalledWith({
      nodeId: 7,
      selectedDates: undefined,
      dayMode: "calendar_day",
    });
    expect(click.mock.instances[0].download).toMatch(/^umsatzbericht_test-festival_agenda-bar_/);
    expect(click.mock.instances[1].download).toMatch(/^finanzbericht_test-festival_agenda-bar_/);
    await waitFor(() => {
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:revenue");
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:accounting");
    });
    click.mockRestore();
  });

  test("uses the shared event-day mode and selected days for both reports", async () => {
    const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    mockGenerateRevenueReport.mockReturnValue({ unwrap: jest.fn().mockResolvedValue("blob:revenue") });
    mockGenerateAccountingReport.mockReturnValue({ unwrap: jest.fn().mockResolvedValue("blob:accounting") });

    render(<NodeReports />);

    fireEvent.click(screen.getByRole("button", { name: "reports.eventDay" }));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "reports.selectDates" }));
    fireEvent.click(screen.getAllByRole("option")[0]);
    fireEvent.click(screen.getAllByRole("option")[1]);
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "reports.downloadRevenue" }));
    fireEvent.click(screen.getByRole("button", { name: "reports.downloadAccounting" }));

    const expectedArgs = {
      nodeId: 7,
      selectedDates: ["2026-01-03", "2026-01-04"],
      dayMode: "event_day",
    };
    await waitFor(() => {
      expect(mockGenerateRevenueReport).toHaveBeenCalledWith(expectedArgs);
      expect(mockGenerateAccountingReport).toHaveBeenCalledWith(expectedArgs);
    });
    click.mockRestore();
  });

  test("offers quick selection for the last seven report days", async () => {
    const click = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    mockGenerateRevenueReport.mockReturnValue({ unwrap: jest.fn().mockResolvedValue("blob:revenue") });

    render(<NodeReports />);

    fireEvent.click(screen.getByText("reports.last7Days"));
    fireEvent.click(screen.getByRole("button", { name: "reports.downloadRevenue" }));

    await waitFor(() => expect(mockGenerateRevenueReport).toHaveBeenCalledTimes(1));
    const args = mockGenerateRevenueReport.mock.calls[0][0];
    expect(args.dayMode).toBe("calendar_day");
    expect(args.selectedDates).toHaveLength(7);
    expect([...args.selectedDates].sort()).toEqual(args.selectedDates);
    click.mockRestore();
  });

  test("disables event days without a configured daily end time", () => {
    mockDailyEndTime = undefined;

    render(<NodeReports />);

    expect((screen.getByRole("button", { name: "reports.eventDay" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("reports.eventDayUnavailable")).not.toBeNull();
  });
});
