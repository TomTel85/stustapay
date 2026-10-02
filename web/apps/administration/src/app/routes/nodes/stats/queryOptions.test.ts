import { configureStore } from "@reduxjs/toolkit";
import { createApi, fakeBaseQuery, setupListeners } from "@reduxjs/toolkit/query";
import { statsQueryOptions } from "./queryOptions";

test("dashboard polling pauses in hidden tabs and refreshes on focus", async () => {
  jest.useFakeTimers();
  const queryFn = jest.fn(async () => ({ data: null }));
  const api = createApi({
    reducerPath: "pollingTest",
    baseQuery: fakeBaseQuery(),
    endpoints: (builder) => ({
      getData: builder.query<null, void>({ queryFn }),
    }),
  });
  const store = configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (getDefaultMiddleware) => getDefaultMiddleware().concat(api.middleware),
  });
  const cleanupListeners = setupListeners(store.dispatch);
  const visibility = jest.spyOn(document, "visibilityState", "get");
  const subscription = store.dispatch(
    api.endpoints.getData.initiate(undefined, { subscriptionOptions: statsQueryOptions(100) })
  );

  try {
    await subscription;
    expect(queryFn).toHaveBeenCalledTimes(1);
    visibility.mockReturnValue("hidden");
    window.dispatchEvent(new Event("visibilitychange"));
    // A poll already scheduled before hiding can still finish; subsequent polls must pause.
    await jest.advanceTimersByTimeAsync(100);
    const callsWhileHidden = queryFn.mock.calls.length;
    await jest.advanceTimersByTimeAsync(1000);
    expect(queryFn).toHaveBeenCalledTimes(callsWhileHidden);
    visibility.mockReturnValue("visible");
    window.dispatchEvent(new Event("focus"));
    await jest.advanceTimersByTimeAsync(100);
    expect(queryFn.mock.calls.length).toBeGreaterThan(callsWhileHidden);
  } finally {
    subscription.unsubscribe();
    cleanupListeners();
    visibility.mockRestore();
    store.dispatch(api.util.resetApiState());
    jest.useRealTimers();
  }
});
