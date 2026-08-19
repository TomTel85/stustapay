import { getGooglePayWidgetOptions } from "./sumUpGooglePay";

describe("getGooglePayWidgetOptions", () => {
  test("passes trimmed production merchant information to the SumUp widget", () => {
    expect(getGooglePayWidgetOptions(" 01234567890123456789 ", " Test Merchant ")).toEqual({
      googlePay: {
        merchantId: "01234567890123456789",
        merchantName: "Test Merchant",
      },
    });
  });

  test("hides Google Pay when production merchant information is incomplete", () => {
    const options = getGooglePayWidgetOptions("", "Test Merchant");

    expect(options.googlePay).toBeUndefined();
    expect(options.onPaymentMethodsLoad?.(["card", " GOOGLE_PAY ", "ideal"])).toEqual(["card", "ideal"]);
  });
});
