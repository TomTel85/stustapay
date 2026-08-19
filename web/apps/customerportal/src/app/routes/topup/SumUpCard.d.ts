export type SumUpResponseType = "sent" | "invalid" | "auth-screen" | "error" | "success";

export interface CardOptions {
  id: string;
  checkoutId: string;
  locale?: string;
  country?: string;
  googlePay?: {
    merchantId: string;
    merchantName: string;
  };
  onPaymentMethodsLoad?: (paymentMethods: string[]) => string[];
  onLoad?: () => void;
  onResponse?: (type: SumUpResponseType, body?: unknown) => void;
}

export interface SumUpCardInstance {
  submit: () => void;
  unmount: () => void;
  update: (cfg: Partial<CardOptions>) => void;
}

export interface SumUpCard {
  mount: (cfg: CardOptions) => SumUpCardInstance;
}

declare global {
  const SumUpCard: SumUpCard;
}
