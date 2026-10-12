import { type CustomerPortalApiConfig } from "@/api";
import { RootState, selectAuthToken } from "@/store";
import type { BaseQueryApi, BaseQueryFn, FetchArgs, FetchBaseQueryError } from "@reduxjs/toolkit/query/react";
import { fetchBaseQuery } from "@reduxjs/toolkit/query/react";
import { z } from "zod";

const siteHost = window.location.host;
const siteProtocol = window.location.protocol;
const customerApiBaseUrl = `${siteProtocol}//${siteHost}/api`;
const customerPortalBaseUrl = window.location.origin;

const prepareAuthHeaders = (
  headers: Headers,
  { getState }: Pick<BaseQueryApi, "getState" | "extra" | "endpoint" | "type" | "forced">
) => {
  const token = selectAuthToken(getState() as RootState);
  headers.set("X-Customer-Portal-Base-Url", customerPortalBaseUrl);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
};

export interface Config {
  customerApiBaseUrl: string;
  apiConfig: CustomerPortalApiConfig;
}

export let config: Config;

const generateConfig = (publicApiConfig: CustomerPortalApiConfig): Config => {
  return {
    customerApiBaseUrl: customerApiBaseUrl,
    apiConfig: publicApiConfig,
  };
};

const publicConfigSchema = z
  .object({
    node_id: z.number().int(),
    currency_identifier: z.string().min(1),
    translation_texts: z.record(z.string(), z.record(z.string(), z.string())),
  })
  .passthrough();

const fetchPublicCustomerApiConfig = async (): Promise<CustomerPortalApiConfig> => {
  const baseUrl = encodeURIComponent(window.location.origin);
  const resp = await fetch(`${customerApiBaseUrl}/config?base_url=${baseUrl}`);
  if (!resp.ok) {
    throw new Error(`Customer portal configuration request failed (${resp.status})`);
  }
  const respJson: unknown = await resp.json();
  return publicConfigSchema.parse(respJson) as CustomerPortalApiConfig;
};

export const fetchConfig = async (): Promise<Config> => {
  const publicConfig = await fetchPublicCustomerApiConfig();
  const c = generateConfig(publicConfig);
  config = c;
  return c;
};

export const customerApiBaseQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (
  args,
  api,
  extraOptions
) => {
  const baseUrl = config.customerApiBaseUrl;
  const rawBaseQuery = fetchBaseQuery({ baseUrl, prepareHeaders: prepareAuthHeaders });
  return rawBaseQuery(args, api, extraOptions);
};
