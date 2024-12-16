import { emptySplitApi as api } from "./emptyApi";
export const addTagTypes = ["auth", "base", "sumup"] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: (build) => ({
      login: build.mutation<LoginApiResponse, LoginApiArg>({
        query: (queryArg) => ({ url: `/auth/login`, method: "POST", body: queryArg.loginPayload }),
        invalidatesTags: ["auth"],
      }),
      logout: build.mutation<LogoutApiResponse, LogoutApiArg>({
        query: () => ({ url: `/auth/logout`, method: "POST" }),
        invalidatesTags: ["auth"],
      }),
      getCustomer: build.query<GetCustomerApiResponse, GetCustomerApiArg>({
        query: () => ({ url: `/customer` }),
        providesTags: ["base"],
      }),
      getOrders: build.query<GetOrdersApiResponse, GetOrdersApiArg>({
        query: () => ({ url: `/orders_with_bon` }),
        providesTags: ["base"],
      }),
      updateCustomerInfo: build.mutation<UpdateCustomerInfoApiResponse, UpdateCustomerInfoApiArg>({
        query: (queryArg) => ({ url: `/customer_info`, method: "POST", body: queryArg.customerBank }),
        invalidatesTags: ["base"],
      }),
      updateCustomerInfoDonateAll: build.mutation<
        UpdateCustomerInfoDonateAllApiResponse,
        UpdateCustomerInfoDonateAllApiArg
      >({
        query: () => ({ url: `/customer_all_donation`, method: "POST" }),
        invalidatesTags: ["base"],
      }),
      payoutInfo: build.query<PayoutInfoApiResponse, PayoutInfoApiArg>({
        query: () => ({ url: `/payout_info` }),
        providesTags: ["base"],
      }),
      getPayoutTransactions: build.query<GetPayoutTransactionsApiResponse, GetPayoutTransactionsApiArg>({
        query: () => ({ url: `/get_payout_transactions` }),
        providesTags: ["base"],
      }),
      getCustomerConfig: build.query<GetCustomerConfigApiResponse, GetCustomerConfigApiArg>({
        query: (queryArg) => ({ url: `/config`, params: { base_url: queryArg.baseUrl } }),
        providesTags: ["base"],
      }),
      getBon: build.query<GetBonApiResponse, GetBonApiArg>({
        query: (queryArg) => ({ url: `/bon/${queryArg.bonId}` }),
        providesTags: ["base"],
      }),
      createCheckout: build.mutation<CreateCheckoutApiResponse, CreateCheckoutApiArg>({
        query: (queryArg) => ({ url: `/sumup/create-checkout`, method: "POST", body: queryArg.createCheckoutPayload }),
        invalidatesTags: ["sumup"],
      }),
      checkCheckout: build.mutation<CheckCheckoutApiResponse, CheckCheckoutApiArg>({
        query: (queryArg) => ({ url: `/sumup/check-checkout`, method: "POST", body: queryArg.checkCheckoutPayload }),
        invalidatesTags: ["sumup"],
      }),
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as api };
export type LoginApiResponse = /** status 200 Successful Response */ LoginResponseRead;
export type LoginApiArg = {
  loginPayload: LoginPayload;
};
export type LogoutApiResponse = unknown;
export type LogoutApiArg = void;
export type GetCustomerApiResponse = /** status 200 Successful Response */ CustomerRead;
export type GetCustomerApiArg = void;
export type GetOrdersApiResponse = /** status 200 Successful Response */ OrderWithBonRead[];
export type GetOrdersApiArg = void;
export type UpdateCustomerInfoApiResponse = /** status 204 Successful Response */ void;
export type UpdateCustomerInfoApiArg = {
  customerBank: CustomerBank;
};
export type UpdateCustomerInfoDonateAllApiResponse = unknown;
export type UpdateCustomerInfoDonateAllApiArg = void;
export type PayoutInfoApiResponse = /** status 200 Successful Response */ PayoutInfo;
export type PayoutInfoApiArg = void;
export type GetPayoutTransactionsApiResponse = /** status 200 Successful Response */ PayoutTransaction[];
export type GetPayoutTransactionsApiArg = void;
export type GetCustomerConfigApiResponse = /** status 200 Successful Response */ CustomerPortalApiConfig;
export type GetCustomerConfigApiArg = {
  baseUrl: string;
};
export type GetBonApiResponse = /** status 200 Successful Response */ any;
export type GetBonApiArg = {
  bonId: number;
};
export type CreateCheckoutApiResponse = /** status 200 Successful Response */ CreateCheckoutResponse;
export type CreateCheckoutApiArg = {
  createCheckoutPayload: CreateCheckoutPayload;
};
export type CheckCheckoutApiResponse = /** status 200 Successful Response */ CheckCheckoutResponse;
export type CheckCheckoutApiArg = {
  checkCheckoutPayload: CheckCheckoutPayload;
};
export type AccountType =
  | "private"
  | "sale_exit"
  | "cash_entry"
  | "cash_exit"
  | "cash_topup_source"
  | "cash_imbalance"
  | "cash_vault"
  | "sumup_entry"
  | "sumup_online_entry"
  | "transport"
  | "cashier"
  | "voucher_create"
  | "donation_exit"
  | "sepa_exit";
export type ProductRestriction = "under_16" | "under_18";
export type UserTagHistoryEntry = {
  user_tag_id: number;
  user_tag_pin: string;
  user_tag_uid: number | null;
  account_id: number;
  comment?: string | null;
  mapping_was_valid_until: string;
};
export type UserTagHistoryEntryRead = {
  user_tag_id: number;
  user_tag_pin: string;
  user_tag_uid: number | null;
  account_id: number;
  comment?: string | null;
  mapping_was_valid_until: string;
  user_tag_uid_hex: string | null;
};
export type Payout = {
  id: number;
  customer_account_id: number;
  iban: string | null;
  account_name: string | null;
  email: string | null;
  user_tag_id: number;
  user_tag_uid: number;
  amount: number;
  donation: number;
  payout_run_id: number;
};
export type PayoutRead = {
  id: number;
  customer_account_id: number;
  iban: string | null;
  account_name: string | null;
  email: string | null;
  user_tag_id: number;
  user_tag_uid: number;
  amount: number;
  donation: number;
  payout_run_id: number;
  user_tag_uid_hex: string | null;
};
export type Customer = {
  node_id: number;
  id: number;
  type: AccountType;
  name: string | null;
  comment: string | null;
  balance: number;
  vouchers: number;
  user_tag_id: number | null;
  user_tag_uid: number | null;
  user_tag_comment?: string | null;
  restriction: ProductRestriction | null;
  tag_history: UserTagHistoryEntry[];
  iban: string | null;
  account_name: string | null;
  email: string | null;
  donation: number | null;
  payout_export: boolean | null;
  user_tag_pin: string | null;
  donate_all: boolean;
  has_entered_info: boolean;
  payout: Payout | null;
};
export type CustomerRead = {
  node_id: number;
  id: number;
  type: AccountType;
  name: string | null;
  comment: string | null;
  balance: number;
  vouchers: number;
  user_tag_id: number | null;
  user_tag_uid: number | null;
  user_tag_comment?: string | null;
  restriction: ProductRestriction | null;
  tag_history: UserTagHistoryEntryRead[];
  iban: string | null;
  account_name: string | null;
  email: string | null;
  donation: number | null;
  payout_export: boolean | null;
  user_tag_pin: string | null;
  donate_all: boolean;
  has_entered_info: boolean;
  payout: PayoutRead | null;
  user_tag_uid_hex: string | null;
};
export type LoginResponse = {
  customer: Customer;
  access_token: string;
  grant_type?: string;
};
export type LoginResponseRead = {
  customer: CustomerRead;
  access_token: string;
  grant_type?: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type LoginPayload = {
  username: string; 
  pin: string;
};
export type PaymentMethod = "cash" | "sumup" | "tag" | "sumup_online";
export type OrderType =
  | "sale"
  | "cancel_sale"
  | "top_up"
  | "pay_out"
  | "ticket"
  | "money_transfer"
  | "money_transfer_imbalance";
export type ProductType = "discount" | "topup" | "payout" | "money_transfer" | "imbalance" | "user_defined" | "ticket";
export type Product = {
  name: string;
  price: number | null;
  fixed_price: boolean;
  price_in_vouchers?: number | null;
  tax_rate_id: number;
  restrictions: ProductRestriction[];
  is_locked: boolean;
  is_returnable: boolean;
  target_account_id?: number | null;
  node_id: number;
  id: number;
  tax_name: string;
  tax_rate: number;
  type: ProductType;
  price_per_voucher?: number | null;
};
export type LineItem = {
  quantity: number;
  product: Product;
  product_price: number;
  tax_rate_id: number;
  tax_name: string;
  tax_rate: number;
  item_id: number;
  total_tax: number;
};
export type LineItemRead = {
  quantity: number;
  product: Product;
  product_price: number;
  tax_rate_id: number;
  tax_name: string;
  tax_rate: number;
  item_id: number;
  total_tax: number;
  total_price: number;
};
export type OrderWithBon = {
  id: number;
  uuid: string;
  total_price: number;
  total_tax: number;
  total_no_tax: number;
  cancels_order: number | null;
  booked_at: string;
  payment_method: PaymentMethod;
  order_type: OrderType;
  cashier_id: number | null;
  till_id: number | null;
  customer_account_id: number | null;
  customer_tag_uid: number | null;
  customer_tag_id: number | null;
  line_items: LineItem[];
  bon_generated: boolean | null;
};
export type OrderWithBonRead = {
  id: number;
  uuid: string;
  total_price: number;
  total_tax: number;
  total_no_tax: number;
  cancels_order: number | null;
  booked_at: string;
  payment_method: PaymentMethod;
  order_type: OrderType;
  cashier_id: number | null;
  till_id: number | null;
  customer_account_id: number | null;
  customer_tag_uid: number | null;
  customer_tag_id: number | null;
  line_items: LineItemRead[];
  bon_generated: boolean | null;
  customer_tag_uid_hex: string | null;
};
export type CustomerBank = {
  iban: string;
  account_name: string;
  email: string;
  donation?: number;
};
export type PayoutInfo = {
  in_payout_run: boolean;
  payout_date: string | null;
};
export type PayoutTransaction = {
  amount: number;
  booked_at: string;
  target_account_name: string;
  target_account_type: string;
  transaction_id: number;
};
export type CustomerPortalApiConfig = {
  test_mode: boolean;
  test_mode_message: string;
  data_privacy_url: string;
  contact_email: string;
  about_page_url: string;
  payout_enabled: boolean;
  currency_identifier: string;
  sumup_topup_enabled: boolean;
  allowed_country_codes: string[] | null;
  translation_texts: {
    [key: string]: {
      [key: string]: string;
    };
  };
  event_name: string;
};
export type CreateCheckoutResponse = {
  checkout_id: string;
};
export type CreateCheckoutPayload = {
  amount: number;
};
export type SumUpCheckoutStatus = "PENDING" | "FAILED" | "PAID";
export type CheckCheckoutResponse = {
  status: SumUpCheckoutStatus;
};
export type CheckCheckoutPayload = {
  checkout_id: string;
};
export const {
  useLoginMutation,
  useLogoutMutation,
  useGetCustomerQuery,
  useLazyGetCustomerQuery,
  useGetOrdersQuery,
  useLazyGetOrdersQuery,
  useUpdateCustomerInfoMutation,
  useUpdateCustomerInfoDonateAllMutation,
  usePayoutInfoQuery,
  useLazyPayoutInfoQuery,
  useGetPayoutTransactionsQuery,
  useLazyGetPayoutTransactionsQuery,
  useGetCustomerConfigQuery,
  useLazyGetCustomerConfigQuery,
  useGetBonQuery,
  useLazyGetBonQuery,
  useCreateCheckoutMutation,
  useCheckCheckoutMutation,
} = injectedRtkApi;
