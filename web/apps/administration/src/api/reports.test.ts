import { configureStore } from "@reduxjs/toolkit";
import { api } from "./api";
import { adminApiBaseQuery } from "./common";

jest.mock("./common", () => ({ adminApiBaseQuery: jest.fn() }));

describe("report download requests", () => {
  const baseQuery = jest.mocked(adminApiBaseQuery);

  beforeEach(() => {
    baseQuery.mockReset();
    baseQuery.mockResolvedValue({ data: "blob:report" });
  });

  test("sends revenue dates and event-day boundaries to the API", async () => {
    const store = configureStore({
      reducer: { [api.reducerPath]: api.reducer },
      middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
    });
    await store
      .dispatch(
        api.endpoints.generateRevenueReport.initiate({
          nodeId: 7,
          selectedDates: ["2026-01-03", "2026-01-05"],
          dayMode: "event_day",
        })
      )
      .unwrap();

    expect(baseQuery.mock.calls[0][0]).toMatchObject({
      url: "/tree/nodes/7/generate-revenue-report",
      method: "POST",
      params: { selected_dates: ["2026-01-03", "2026-01-05"], day_mode: "event_day" },
    });
  });

  test("preserves every accounting filter in the API request", async () => {
    const store = configureStore({
      reducer: { [api.reducerPath]: api.reducer },
      middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
    });
    await store
      .dispatch(
        api.endpoints.generateAccountingReport.initiate({
          nodeId: 7,
          selectedDates: ["2026-01-03"],
          dayMode: "event_day",
          fromTimestamp: "2026-01-03T00:00:00Z",
          toTimestamp: "2026-01-04T00:00:00Z",
          tillId: 8,
          subnodeId: 9,
        })
      )
      .unwrap();

    expect(baseQuery.mock.calls[0][0]).toMatchObject({
      url: "/tree/nodes/7/generate-accounting-report",
      method: "POST",
      params: {
        selected_dates: ["2026-01-03"],
        day_mode: "event_day",
        till_id: 8,
        subnode_id: 9,
        from_timestamp: "2026-01-03T00:00:00Z",
        to_timestamp: "2026-01-04T00:00:00Z",
      },
    });
  });
});
