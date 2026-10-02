import type { CurrentUser } from "@/api";
import { api } from "@/api";
import { configureStore } from "@reduxjs/toolkit";
import { authSlice } from "./authSlice";
import { sessionMiddleware } from "./sessionMiddleware";

jest.mock("@/api", () => ({
  api: {
    util: { resetApiState: jest.fn(() => ({ type: "api/reset" })) },
    endpoints: Object.fromEntries(
      ["login", "logout", "changePassword", "changeUserPassword"].map((endpoint) => [
        endpoint,
        {
          matchFulfilled: (action: { type: string }) => action.type === `${endpoint}/fulfilled`,
          matchRejected: (action: { type: string }) => action.type === `${endpoint}/rejected`,
        },
      ])
    ),
  },
}));

const user: CurrentUser = { id: 42, node_id: 1, login: "admin", display_name: "Admin", privileges: [] };
const authenticated = { user, token: "old-session" };

describe("password credential revocation", () => {
  beforeEach(() => jest.clearAllMocks());
  it("clears the persisted session after a successful password change", () => {
    expect(authSlice.reducer(authenticated, { type: "changePassword/fulfilled" })).toEqual({ user: null, token: null });
  });

  it("keeps the session when a password change fails", () => {
    expect(authSlice.reducer(authenticated, { type: "changePassword/rejected" })).toEqual(authenticated);
  });

  it("clears the session when an administrator resets their own password", () => {
    expect(authSlice.reducer(authenticated, { type: "changeUserPassword/fulfilled", payload: user })).toEqual({
      user: null,
      token: null,
    });
  });

  it("keeps the administrator's session when resetting another user's password", () => {
    expect(
      authSlice.reducer(authenticated, { type: "changeUserPassword/fulfilled", payload: { ...user, id: 43 } })
    ).toEqual(authenticated);
  });

  it("clears cached API data when credentials are revoked", () => {
    const store = configureStore({
      reducer: { auth: authSlice.reducer },
      preloadedState: { auth: authenticated },
      middleware: (defaults) => defaults().concat(sessionMiddleware),
    });
    store.dispatch({ type: "changePassword/fulfilled" });
    expect(api.util.resetApiState).toHaveBeenCalledTimes(1);
  });

  it("clears cached API data when a different session signs in", () => {
    const store = configureStore({
      reducer: { auth: authSlice.reducer },
      preloadedState: { auth: authenticated },
      middleware: (defaults) => defaults().concat(sessionMiddleware),
    });
    store.dispatch({ type: "login/fulfilled", payload: { success: { user, token: "new-session" } } });
    expect(api.util.resetApiState).toHaveBeenCalledTimes(1);
  });

  it("keeps cached API data when authentication has not changed", () => {
    const store = configureStore({
      reducer: { auth: authSlice.reducer },
      preloadedState: { auth: authenticated },
      middleware: (defaults) => defaults().concat(sessionMiddleware),
    });
    store.dispatch({ type: "changePassword/rejected" });
    expect(api.util.resetApiState).not.toHaveBeenCalled();
  });
});
