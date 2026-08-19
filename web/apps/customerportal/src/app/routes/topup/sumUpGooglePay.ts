import type { CardOptions } from "./SumUpCard";

type GooglePayWidgetOptions = Pick<CardOptions, "googlePay" | "onPaymentMethodsLoad">;

const normalizePaymentMethod = (paymentMethod: string) => paymentMethod.trim().toLowerCase();

export const getGooglePayWidgetOptions = (
  merchantId: string | null | undefined,
  merchantName: string | null | undefined
): GooglePayWidgetOptions => {
  const normalizedMerchantId = merchantId?.trim();
  const normalizedMerchantName = merchantName?.trim();

  if (normalizedMerchantId && normalizedMerchantName) {
    return {
      googlePay: {
        merchantId: normalizedMerchantId,
        merchantName: normalizedMerchantName,
      },
    };
  }

  return {
    onPaymentMethodsLoad: (paymentMethods) =>
      paymentMethods.filter((paymentMethod) => normalizePaymentMethod(paymentMethod) !== "google_pay"),
  };
};
