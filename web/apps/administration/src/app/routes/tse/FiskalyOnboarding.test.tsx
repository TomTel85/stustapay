import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const mockUseCurrentUserHasPrivilege = jest.fn();
const mockUseCurrentUserHasPrivilegeAtNode = jest.fn();
const mockUseListFiskalySitesQuery = jest.fn();
const mockUseGetFiskalySiteStatusQuery = jest.fn();
const mockUseCreateFiskalySiteMutation = jest.fn();
const mockUseStartFiskalyProvisioningMutation = jest.fn();
const mockUseRetryFiskalyProvisioningMutation = jest.fn();
const mockRefetchTses = jest.fn();
const mockSetPaused = jest.fn();

jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({ currentNode: mockCurrentNode }),
  useCurrentUserHasPrivilege: (...args: unknown[]) => mockUseCurrentUserHasPrivilege(...args),
  useCurrentUserHasPrivilegeAtNode: (...args: unknown[]) => mockUseCurrentUserHasPrivilegeAtNode(...args),
}));

jest.mock("@/api", () => ({
  useNodeTree: () => ({ root: mockNodeTree }),
  useListTsesQuery: () => ({ refetch: mockRefetchTses }),
}));

jest.mock("@/api/fiskaly", () => ({
  useListFiskalySitesQuery: (...args: unknown[]) => mockUseListFiskalySitesQuery(...args),
  useGetFiskalySiteStatusQuery: (...args: unknown[]) => mockUseGetFiskalySiteStatusQuery(...args),
  useCreateFiskalySiteMutation: (...args: unknown[]) => mockUseCreateFiskalySiteMutation(...args),
  useSetFiskalyProvisioningPausedMutation: () => [mockSetPaused, { isLoading: false }],
  useStartFiskalyProvisioningMutation: (...args: unknown[]) => mockUseStartFiskalyProvisioningMutation(...args),
  useRetryFiskalyProvisioningMutation: (...args: unknown[]) => mockUseRetryFiskalyProvisioningMutation(...args),
}));

jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const mockEventNode = {
  id: 12,
  name: "Event Twelve",
  event_node_id: 12,
  event: { id: 12, bon_issuer: "Example operator", bon_address: "Long-form address, Berlin", ust_id: "DE123" },
  privileges_at_node: ["node_administration"],
};
const mockCustomerNode = { id: 4, event_node_id: null, name: "Customer Four", children: [] };
const mockNodeTree = { id: 0, privileges_at_node: ["node_administration"], children: [mockCustomerNode] };
let mockCurrentNode = mockEventNode;

const site = {
  id: 7,
  customer_node_id: 4,
  name: "Main venue",
  operator_name: "Example GmbH",
  address_line1: "Main Street 1",
  zip: "12345",
  town: "Berlin",
  country_code: "DEU",
  vat_id: null,
  organization_id: null,
};
const failedJob = {
  id: 8,
  site_id: 7,
  event_node_id: 12,
  environment: "TEST" as const,
  status: "failed" as const,
  step: "create_tse",
  last_error: "Remote operation failed",
  tse_id: null,
  attempts: 1,
};
const readyJob = { ...failedJob, status: "ready" as const, last_error: null };

const mockRefetch = jest.fn();
const mockRefetchJobs = jest.fn();
const mockCreateSite = jest.fn();
const mockStart = jest.fn();
const mockRetry = jest.fn();

const { MemoryRouter } = require("react-router-dom");
const { FiskalyOnboarding } = require("./FiskalyOnboarding");

describe("FiskalyOnboarding", () => {
  beforeEach(() => {
    mockCurrentNode = mockEventNode;
    mockUseCurrentUserHasPrivilege.mockReset().mockReturnValue(true);
    mockUseCurrentUserHasPrivilegeAtNode.mockReset().mockReturnValue(() => true);
    mockUseListFiskalySitesQuery.mockReset().mockReturnValue({ data: [site], isLoading: false, refetch: mockRefetch });
    mockUseGetFiskalySiteStatusQuery.mockReset().mockReturnValue({ data: [], refetch: mockRefetchJobs });
    mockRefetchTses.mockReset();
    mockCreateSite.mockReset().mockReturnValue({ unwrap: jest.fn().mockResolvedValue(site) });
    mockStart.mockReset().mockReturnValue({ unwrap: jest.fn().mockResolvedValue(readyJob) });
    mockRetry.mockReset().mockReturnValue({ unwrap: jest.fn().mockResolvedValue(readyJob) });
    mockUseCreateFiskalySiteMutation.mockReset().mockReturnValue([mockCreateSite, { isLoading: false }]);
    mockUseStartFiskalyProvisioningMutation.mockReset().mockReturnValue([mockStart, { isLoading: false }]);
    mockUseRetryFiskalyProvisioningMutation.mockReset().mockReturnValue([mockRetry, { isLoading: false }]);
  });

  it("shows provisioning controls only for a root node administrator", () => {
    mockUseCurrentUserHasPrivilegeAtNode.mockReturnValue((nodeId: number) => nodeId === 0);
    const { rerender } = render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);

    expect(screen.getByRole("button", { name: "tse.fiskalyOnboarding.startTest" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "tse.fiskalyOnboarding.startLive" })).toBeNull();

    mockUseCurrentUserHasPrivilegeAtNode.mockReturnValue(() => false);
    rerender(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);

    expect(screen.queryByRole("button", { name: "tse.fiskalyOnboarding.startTest" })).toBeNull();
    expect(screen.queryByRole("button", { name: "tse.fiskalyOnboarding.addSite" })).toBeNull();
  });

  it("lets a customer administrator read setup status without mutation controls", async () => {
    mockUseCurrentUserHasPrivilegeAtNode.mockReturnValue(() => false);
    mockUseGetFiskalySiteStatusQuery.mockReturnValue({ data: [readyJob], refetch: mockRefetchJobs });
    render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "tse.fiskalyOnboarding.site" }));
    fireEvent.click(await screen.findByRole("option", { name: /Main venue/ }));

    expect(screen.getByText("TEST · tse.fiskalyOnboarding.status.ready · create_tse")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "tse.fiskalyOnboarding.startTest" })).toBeNull();
    expect(screen.queryByRole("button", { name: "tse.fiskalyOnboarding.retry" })).toBeNull();
  });

  it("warns when an ended deployment still has registered clients near month-end", () => {
    mockUseGetFiskalySiteStatusQuery.mockReturnValue({
      data: [{ ...readyJob, month_end_registered_clients: 2 }],
      refetch: mockRefetchJobs,
    });
    render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);

    expect(screen.getByRole("alert").textContent).toContain("tse.fiskalyOnboarding.monthEndWarning");
  });

  it("starts TEST provisioning", async () => {
    render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "tse.fiskalyOnboarding.site" }));
    fireEvent.click(await screen.findByRole("option", { name: /Main venue/ }));

    fireEvent.click(screen.getByRole("button", { name: "tse.fiskalyOnboarding.startTest" }));
    await waitFor(() => expect(mockStart).toHaveBeenCalledWith({
      nodeId: 12,
      newFiskalyProvisioningJob: { site_id: 7, event_node_id: 12, environment: "TEST" },
    }));

  });

  it("pauses a ready deployment using its existing setup ID", async () => {
    mockSetPaused.mockReturnValue({ unwrap: async () => readyJob });
    mockUseGetFiskalySiteStatusQuery.mockReturnValue({ data: [readyJob], refetch: mockRefetchJobs });
    render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "tse.fiskalyOnboarding.site" }));
    fireEvent.click(await screen.findByRole("option", { name: /Main venue/ }));
    fireEvent.click(screen.getByRole("button", { name: "tse.fiskalyOnboarding.pause" }));
    await waitFor(() => expect(mockSetPaused).toHaveBeenCalledWith({ nodeId: 12, jobId: readyJob.id, paused: true }));
  });

  it("prefills event operator and address details without parsing the address", async () => {
    render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button", { name: "tse.fiskalyOnboarding.addSite" }));

    expect(screen.getByRole("textbox", { name: "tse.fiskalyOnboarding.siteName" })).toHaveProperty("value", "Event Twelve");
    expect(screen.getByRole("textbox", { name: "tse.fiskalyOnboarding.operator" })).toHaveProperty("value", "Example operator");
    expect(screen.getByRole("textbox", { name: "tse.fiskalyOnboarding.address" })).toHaveProperty("value", "Long-form address, Berlin");
    expect(screen.getByRole("textbox", { name: "tse.fiskalyOnboarding.vatId" })).toHaveProperty("value", "DE123");

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "tse.fiskalyOnboarding.customer" }));
    fireEvent.click(await screen.findByRole("option", { name: "Customer Four" }));
    fireEvent.change(screen.getByRole("textbox", { name: "tse.fiskalyOnboarding.zip" }), { target: { value: "12345" } });
    fireEvent.change(screen.getByRole("textbox", { name: "tse.fiskalyOnboarding.town" }), { target: { value: "Berlin" } });
    fireEvent.click(screen.getByRole("button", { name: "tse.fiskalyOnboarding.saveSite" }));

    await waitFor(() => expect(mockCreateSite).toHaveBeenCalledWith({
      nodeId: 12,
      newFiskalySite: {
        customer_node_id: 4,
        name: "Event Twelve",
        operator_name: "Example operator",
        address_line1: "Long-form address, Berlin",
        zip: "12345",
        town: "Berlin",
        country_code: "DEU",
        vat_id: "DE123",
      },
    }));
  });

  it("keeps start disabled without a selected site or an event node", async () => {
    const { rerender } = render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "tse.fiskalyOnboarding.startTest" })).toHaveProperty("disabled", true);

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "tse.fiskalyOnboarding.site" }));
    fireEvent.click(await screen.findByRole("option", { name: /Main venue/ }));
    expect(screen.getByRole("button", { name: "tse.fiskalyOnboarding.startTest" })).toHaveProperty("disabled", false);

    mockCurrentNode = { ...mockEventNode, event: null, event_node_id: null };
    rerender(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "tse.fiskalyOnboarding.startTest" })).toHaveProperty("disabled", true);
  });

  it("shows status errors and lets root administrators retry failed jobs", async () => {
    mockUseGetFiskalySiteStatusQuery.mockReturnValue({ data: [failedJob], refetch: mockRefetchJobs, error: true });
    render(<MemoryRouter><FiskalyOnboarding /></MemoryRouter>);
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "tse.fiskalyOnboarding.site" }));
    fireEvent.click(await screen.findByRole("option", { name: /Main venue/ }));

    expect(screen.getByText("tse.fiskalyOnboarding.statusError")).toBeTruthy();
    expect(screen.getByText("Remote operation failed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "tse.fiskalyOnboarding.retry" }));
    await waitFor(() => expect(mockRetry).toHaveBeenCalledWith({ nodeId: 12, jobId: 8 }));
  });
});
