import { api } from "@/api";
import type { Middleware } from "@reduxjs/toolkit";
import { selectAuthToken } from "./authSlice";
import type { RootState } from "./store";

export const sessionMiddleware: Middleware = (store) => (next) => (action) => {
  const previousToken = selectAuthToken(store.getState() as RootState);
  const result = next(action);
  if (previousToken !== selectAuthToken(store.getState() as RootState)) {
    store.dispatch(api.util.resetApiState());
  }
  return result;
};
