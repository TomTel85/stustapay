import { configureStore } from "@reduxjs/toolkit";
import { toast } from "react-toastify";
import { errorMiddleware } from "./errorMiddleware";

jest.mock("@/api", () => ({
  api: {
    endpoints: {
      deleteUser: {
        matchRejected: (action: { type: string }) => action.type === "deleteUser/rejected",
      },
    },
  },
}));
jest.mock("@/i18n", () => ({ t: (key: string) => key }));
jest.mock("./authSlice", () => ({ forceLogout: () => ({ type: "auth/forceLogout" }) }));
jest.mock("react-toastify", () => ({ toast: { error: jest.fn() } }));

test.each([
  [{ status: "FETCH_ERROR", error: "Failed to fetch" }, "deleteUserFailed"],
  [{ status: 404, data: { detail: "Not Found" } }, "deleteUserFailed"],
  [{ status: 403, data: { id: "error", type: "access-denied", message: "Access denied" } }, "403: Access denied"],
])("shows one message for a rejected user deletion (%j)", (payload, message) => {
  jest.clearAllMocks();
  const consoleError = jest.spyOn(console, "error").mockImplementation(() => undefined);
  const store = configureStore({ reducer: () => null, middleware: (defaults) => defaults().concat(errorMiddleware) });

  try {
    store.dispatch({
      type: "deleteUser/rejected",
      payload,
      meta: { requestId: "delete-user", requestStatus: "rejected", rejectedWithValue: true },
    });
    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith(message);
  } finally {
    consoleError.mockRestore();
  }
});
