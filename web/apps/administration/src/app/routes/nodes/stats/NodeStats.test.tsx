import * as React from "react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import { DateTime } from "luxon";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const mockCurrencyFormatter = (amount: number) => `EUR ${amount}`;

const mockUseCurrentUserHasPrivilege = jest.fn();
const mockDispatch = jest.fn();
const mockUseGetAvailableDatesQuery = jest.fn();
const mockUseListTillsQuery = jest.fn();
const mockUseListProductsQuery = jest.fn();
const mockUseGetRevenuePredictionQuery = jest.fn();
const mockUseGetDashboardOverviewQuery = jest.fn();
const mockUseGetPaymentMethodStatsQuery = jest.fn();
const mockUseGetProductStatsQuery = jest.fn();
const mockUseGetRevenueByCounterQuery = jest.fn();
const mockInvalidateTags = jest.fn();

let mockUiState = {
  statsPollingIntervalMs: 0,
  statsExpandedSections: {
    filters: false,
    kpis: false,
    prediction: false,
    counterChart: false,
    productChart: false,
    quantityTable: false,
    counterTable: false,
    orders: true,
  },
};

jest.mock("@/hooks", () => ({
  useCurrentEventSettings: () => ({
    eventSettings: {
      start_date: "2026-01-01",
      end_date: "2026-01-07",
      daily_end_time: "06:00:00",
      bon_title: "Test Festival",
    },
  }),
  useCurrentNode: () => ({
    currentNode: {
      id: 5,
      name: "Eventbereich",
      event: {},
      event_node_id: 5,
      children: [],
    },
  }),
  useCurrencyFormatter: () => mockCurrencyFormatter,
  useCurrentUserHasPrivilege: (...args: unknown[]) => mockUseCurrentUserHasPrivilege(...args),
}));

const mockUiStateWrapper = {
  get ui() {
    return mockUiState;
  },
};

jest.mock("@/store", () => ({
  useAppDispatch: () => mockDispatch,
  useAppSelector: (selector: (state: typeof mockUiStateWrapper) => unknown) => selector(mockUiStateWrapper),
  selectStatsPollingInterval: (state: { ui: { statsPollingIntervalMs: number } }) => state.ui.statsPollingIntervalMs,
  selectStatsExpandedSections: (state: { ui: { statsExpandedSections: unknown } }) => state.ui.statsExpandedSections,
  setStatsPollingInterval: jest.fn(),
  setStatsSectionExpanded: jest.fn(),
}));

jest.mock("@/api", () => ({
  api: { util: { invalidateTags: (...args: unknown[]) => mockInvalidateTags(...args) } },
  useGetAvailableDatesQuery: (...args: unknown[]) => mockUseGetAvailableDatesQuery(...args),
  useListTillsQuery: (...args: unknown[]) => mockUseListTillsQuery(...args),
  useListProductsQuery: (...args: unknown[]) => mockUseListProductsQuery(...args),
  useGetRevenuePredictionQuery: (...args: unknown[]) => mockUseGetRevenuePredictionQuery(...args),
  useGetDashboardOverviewQuery: (...args: unknown[]) => mockUseGetDashboardOverviewQuery(...args),
  useGetPaymentMethodStatsQuery: (...args: unknown[]) => mockUseGetPaymentMethodStatsQuery(...args),
  useGetProductStatsQuery: (...args: unknown[]) => mockUseGetProductStatsQuery(...args),
  useGetRevenueByCounterQuery: (...args: unknown[]) => mockUseGetRevenueByCounterQuery(...args),
}));

jest.mock("./RevenueByCounterChart", () => ({
  RevenueByCounterChart: (props: { enabled?: boolean }) => (
    <div data-testid="counter-chart">{props.enabled ? "enabled" : "disabled"}</div>
  ),
}));

jest.mock("./RevenueByProductChart", () => ({
  RevenueByProductChart: (props: { enabled?: boolean }) => (
    <div data-testid="product-chart">{props.enabled ? "enabled" : "disabled"}</div>
  ),
}));

jest.mock("./RevenueByCounterTable", () => ({
  RevenueByCounterTable: (props: { enabled?: boolean }) => (
    <div data-testid="counter-table">{props.enabled ? "enabled" : "disabled"}</div>
  ),
}));

jest.mock("./QuantitiesByProductTable", () => ({
  QuantitiesByProductTable: (props: { enabled?: boolean }) => (
    <div data-testid="quantities-table">{props.enabled ? "enabled" : "disabled"}</div>
  ),
}));

jest.mock("./OrdersTable", () => ({
  OrdersTable: (props: { enabled?: boolean }) => (
    <div data-testid="orders-table">{props.enabled ? "enabled" : "disabled"}</div>
  ),
}));

jest.mock("./RevenuePredictionChart", () => ({
  RevenuePredictionChart: () => <div>prediction-chart</div>,
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

const { MemoryRouter } = require("react-router-dom");
const { NodeStats } = require("./NodeStats");

describe("NodeStats", () => {
  const expectedFromTimestamp = DateTime.fromISO("2026-01-03T06:00:00", { zone: "Europe/Berlin" }).toISO();
  const expectedToTimestamp = DateTime.fromISO("2026-01-04T05:59:59.999", { zone: "Europe/Berlin" }).toISO();

  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(new Date("2026-01-03T12:00:00.000Z"));
    mockUiState = {
      statsPollingIntervalMs: 0,
      statsExpandedSections: {
        filters: false,
        kpis: false,
        prediction: false,
        counterChart: false,
        productChart: false,
        quantityTable: false,
        counterTable: false,
        orders: false,
      },
    };
    mockUseCurrentUserHasPrivilege.mockReset();
    mockDispatch.mockReset();
    mockUseGetAvailableDatesQuery.mockReset();
    mockUseListTillsQuery.mockReset();
    mockUseListProductsQuery.mockReset();
    mockUseGetRevenuePredictionQuery.mockReset();
    mockUseGetDashboardOverviewQuery.mockReset();
    mockUseGetPaymentMethodStatsQuery.mockReset();
    mockUseGetProductStatsQuery.mockReset();
    mockUseGetRevenueByCounterQuery.mockReset();
    mockInvalidateTags.mockReset();

    mockUseCurrentUserHasPrivilege.mockImplementation((privilege: unknown) => {
      if (Array.isArray(privilege)) {
        return privilege.includes("can_book_orders");
      }
      return privilege === "view_node_stats" || privilege === "can_book_orders";
    });

    mockUseGetAvailableDatesQuery.mockReturnValue({ currentData: [] });
    mockUseListTillsQuery.mockReturnValue({ currentData: { ids: [], entities: {} } });
    mockUseListProductsQuery.mockReturnValue({ currentData: { ids: [], entities: {} } });
    mockUseGetRevenuePredictionQuery.mockReturnValue({ isFetching: false, isError: false });
    mockUseGetDashboardOverviewQuery.mockReturnValue({ isFetching: false, isError: false });
    mockUseGetPaymentMethodStatsQuery.mockReturnValue({ isFetching: false, isError: false });
    mockUseGetProductStatsQuery.mockReturnValue({ isFetching: false, isError: false });
    mockUseGetRevenueByCounterQuery.mockReturnValue({ isFetching: false, isError: false });
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test("starts with more filters collapsed on every visit, even with an old saved preference", () => {
    mockUiState.statsExpandedSections.filters = true;
    const visit = () =>
      render(
        <MemoryRouter initialEntries={["/node/5/stats"]}>
          <NodeStats />
        </MemoryRouter>
      );
    const filters = () => screen.getByRole("button", { name: "overview.moreStatsSettings" });

    const firstVisit = visit();
    expect(filters().getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(filters());
    expect(filters().getAttribute("aria-expanded")).toBe("true");
    expect(mockDispatch).not.toHaveBeenCalled();

    firstVisit.unmount();
    visit();
    expect(filters().getAttribute("aria-expanded")).toBe("false");
  });

  test("initializes event pages to the current business day and skips collapsed section queries", () => {
    render(
      <MemoryRouter initialEntries={["/node/5/stats"]}>
        <NodeStats />
      </MemoryRouter>
    );

    expect(mockUseGetDashboardOverviewQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        fromTimestamp: expectedFromTimestamp,
        toTimestamp: expectedToTimestamp,
      }),
      expect.objectContaining({ skip: true })
    );
    expect(mockUseGetProductStatsQuery).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({ skip: true })
    );
    expect(mockUseGetRevenueByCounterQuery).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({ skip: true })
    );
    expect(mockUseGetAvailableDatesQuery).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({ skip: true })
    );
    expect(screen.getByTestId("orders-table").textContent).toContain("disabled");
    expect(screen.getByRole("combobox", { name: "overview.reportingPeriod" }).textContent).toContain("overview.today");
  });

  test("fetches only the expanded sections and shares one top-level product/counter query", () => {
    mockUiState = {
      statsPollingIntervalMs: 30000,
      statsExpandedSections: {
        filters: true,
        kpis: true,
        prediction: false,
        counterChart: true,
        productChart: true,
        quantityTable: true,
        counterTable: true,
        orders: false,
      },
    };

    render(
      <MemoryRouter initialEntries={["/node/5/stats"]}>
        <NodeStats />
      </MemoryRouter>
    );

    expect(mockUseGetAvailableDatesQuery).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({ skip: true })
    );
    expect(mockUseGetDashboardOverviewQuery).toHaveBeenCalledTimes(1);
    expect(mockUseGetPaymentMethodStatsQuery).toHaveBeenCalledTimes(1);
    expect(mockUseGetProductStatsQuery).toHaveBeenCalledTimes(1);
    expect(mockUseGetRevenueByCounterQuery).toHaveBeenCalledTimes(1);
    expect(mockUseGetProductStatsQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        fromTimestamp: expectedFromTimestamp,
        toTimestamp: expectedToTimestamp,
      }),
      expect.objectContaining({ skip: false, pollingInterval: 30000, skipPollingIfUnfocused: true })
    );
    expect(mockUseGetRevenueByCounterQuery).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({ skip: false, pollingInterval: 30000, skipPollingIfUnfocused: true })
    );

    expect(screen.getByTestId("product-chart").textContent).toContain("enabled");
    expect(screen.getByTestId("counter-chart").textContent).toContain("enabled");
    expect(screen.getByTestId("counter-table").textContent).toContain("enabled");
    expect(screen.getByTestId("quantities-table").textContent).toContain("enabled");
    expect(screen.getByTestId("orders-table").textContent).toContain("disabled");
  });

  test("advances an open dashboard to the next business day at the configured cutoff", () => {
    jest.setSystemTime(DateTime.fromISO("2026-01-04T05:59:59.500", { zone: "Europe/Berlin" }).toJSDate());
    render(
      <MemoryRouter initialEntries={["/node/5/stats"]}>
        <NodeStats />
      </MemoryRouter>
    );

    expect(mockUseGetDashboardOverviewQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({ fromTimestamp: expectedFromTimestamp }),
      expect.any(Object)
    );
    act(() => jest.advanceTimersByTime(500));
    expect(mockUseGetDashboardOverviewQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({
        fromTimestamp: DateTime.fromISO("2026-01-04T06:00:00", { zone: "Europe/Berlin" }).toISO(),
      }),
      expect.any(Object)
    );
  });

  test("does not show broader totals for a product with no sales", () => {
    mockUiState.statsExpandedSections.kpis = true;
    mockUseGetDashboardOverviewQuery.mockReturnValue({
      currentData: {
        total_revenue: 100,
        guests_with_orders: 10,
        total_guest_credit: 500,
        guests_with_credit: 10,
        guests_paid_out: 0,
        online_donation: 0,
        online_for_payout: 0,
      },
    });
    mockUseGetProductStatsQuery.mockReturnValue({
      currentData: { product_overall_stats: [], deposit_overall_stats: [] },
    });
    mockUseListProductsQuery.mockReturnValue({
      currentData: { ids: [6], entities: { 6: { id: 6, name: "Unsold tea" } } },
    });
    render(
      <MemoryRouter initialEntries={["/node/5/stats"]}>
        <NodeStats />
      </MemoryRouter>
    );

    expect(screen.getByText("EUR 100")).toBeTruthy();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "overview.filterProduct" }));
    fireEvent.click(screen.getByRole("option", { name: "Unsold tea" }));
    expect(screen.queryByText("EUR 100")).toBeNull();
    expect(screen.getByText("overview.noProductSales")).toBeTruthy();
  });

  test("distinguishes a failed refresh from missing results for a new scope", () => {
    mockUiState.statsExpandedSections.kpis = true;
    const refetch = jest.fn();
    const overview = {
      total_revenue: 100,
      guests_with_orders: 10,
      total_guest_credit: 500,
      guests_with_credit: 10,
      guests_paid_out: 0,
      online_donation: 0,
      online_for_payout: 0,
    };
    mockUseGetDashboardOverviewQuery.mockReturnValue({
      data: overview,
      isError: true,
      refetch,
    });
    const app = () => (
      <MemoryRouter initialEntries={["/node/5/stats"]}>
        <NodeStats />
      </MemoryRouter>
    );
    const { rerender } = render(app());
    expect(screen.getByText("overview.statsLoadFailed")).toBeTruthy();
    expect(screen.queryByText("EUR 100")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "overview.retryStats" }));
    expect(refetch).toHaveBeenCalledTimes(1);

    mockUseGetDashboardOverviewQuery.mockReturnValue({
      currentData: overview,
      isError: true,
      refetch,
      fulfilledTimeStamp: 100,
    });
    rerender(app());
    expect(screen.getByText("overview.statsStale")).toBeTruthy();
    expect(screen.getByText("overview.lastUpdated")).toBeTruthy();
    expect(screen.getByText("EUR 100")).toBeTruthy();
  });

  test("shows the orders section for stats viewers with can_book_orders", () => {
    mockUiState = {
      statsPollingIntervalMs: 0,
      statsExpandedSections: {
        filters: false,
        kpis: false,
        prediction: false,
        counterChart: false,
        productChart: false,
        quantityTable: false,
        counterTable: false,
        orders: true,
      },
    };

    render(
      <MemoryRouter initialEntries={["/node/5/stats"]}>
        <NodeStats />
      </MemoryRouter>
    );

    const ordersAccordion =
      screen.getByText("overview.orders").closest("[class*=MuiAccordion]") ??
      screen.getByText("overview.orders").parentElement;
    expect(ordersAccordion).toBeTruthy();
    expect(screen.getByTestId("orders-table")).toBeTruthy();
    expect(within(screen.getByTestId("orders-table")).getByText("enabled")).toBeTruthy();
  });
});
