import * as React from "react";
import { render, screen } from "@testing-library/react";
import { Form, Formik } from "formik";
import { TillProfileForm } from "./TillProfileForm";

jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({
    currentNode: {
      id: 1,
    },
  }),
}));

jest.mock("@/api", () => ({
  useListTillLayoutsQuery: () => ({
    layouts: [],
  }),
  selectTillLayoutAll: () => [],
}));

jest.mock("@stustapay/components", () => ({
  Select: () => <div data-testid="layout-select" />,
}));

jest.mock("@stustapay/form-components", () => ({
  FormTextField: () => <input />,
  FormCheckbox: ({
    name,
    label,
    disabled,
    formik,
  }: {
    name: string;
    label: string;
    disabled?: boolean;
    formik: { values: Record<string, boolean>; setFieldValue: (field: string, value: boolean) => void };
  }) => (
    <input
      type="checkbox"
      aria-label={label}
      checked={formik.values[name] ?? false}
      disabled={disabled}
      onChange={(event) => formik.setFieldValue(name, event.target.checked)}
    />
  ),
}));

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("TillProfileForm", () => {
  const renderForm = (enableCardPayment: boolean, tapToPayEnabled: boolean) =>
    render(
      <Formik
        initialValues={{
          name: "Profile",
          description: null,
          layout_id: 1,
          allow_top_up: false,
          allow_cash_out: false,
          allow_ticket_sale: false,
          allow_ticket_vouchers: false,
          enable_ssp_payment: true,
          enable_cash_payment: false,
          enable_card_payment: enableCardPayment,
          tap_to_pay_enabled: tapToPayEnabled,
        }}
        onSubmit={jest.fn()}
      >
        {(formik) => (
          <Form>
            <TillProfileForm {...formik} />
          </Form>
        )}
      </Formik>
    );

  test("enables Tap to Pay configuration for card-enabled till profiles", () => {
    renderForm(true, true);

    const checkbox = screen.getByLabelText("profile.tapToPayEnabled") as HTMLInputElement;
    expect(checkbox.disabled).toBe(false);
    expect(checkbox.checked).toBe(true);
  });

  test("disables Tap to Pay configuration when card payments are disabled", () => {
    renderForm(false, false);

    const checkbox = screen.getByLabelText("profile.tapToPayEnabled") as HTMLInputElement;
    expect(checkbox.disabled).toBe(true);
    expect(checkbox.checked).toBe(false);
  });
});
