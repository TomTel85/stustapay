import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Form, Formik } from "formik";
import { TextDecoder, TextEncoder } from "util";
import { NewTseSchema, UpdateTseSchema } from "@stustapay/models";

(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextEncoder =
  TextEncoder;
(globalThis as typeof globalThis & { TextEncoder: typeof TextEncoder; TextDecoder: typeof TextDecoder }).TextDecoder =
  TextDecoder;

const { toFormikValidationSchema } = require("@stustapay/utils");
const { TseForm } = require("./TseForm");
const { UpdateTseForm } = require("./UpdateTseForm");

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const newTseInitialValues = {
  name: "",
  type: "diebold_nixdorf" as const,
  serial: "",
  ws_url: "",
  ws_timeout: 5,
  password: "",
  fiskaly_profile: null,
};

describe("TSE provider forms", () => {
  it("switches the create form between USB fields and a Fiskaly profile without exposing credentials", async () => {
    render(
      <Formik initialValues={newTseInitialValues} onSubmit={jest.fn()}>
        {(formik) => <TseForm {...formik} />}
      </Formik>
    );

    expect(screen.getByLabelText("tse.serial")).toBeTruthy();
    expect(screen.getByLabelText("tse.wsUrl")).toBeTruthy();
    expect(screen.getByLabelText("tse.password")).toBeTruthy();

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "tse.type" }));
    fireEvent.click(await screen.findByRole("option", { name: "tse.provider.fiskaly" }));

    expect(await screen.findByLabelText("tse.fiskalyProfile")).toBeTruthy();
    expect(screen.queryByLabelText("tse.serial")).toBeNull();
    expect(screen.queryByLabelText("tse.wsUrl")).toBeNull();
    expect(screen.queryByLabelText("tse.password")).toBeNull();
    expect(screen.queryByLabelText(/credential|secret|token|api key/i)).toBeNull();
  });

  it("keeps USB fields on the create form and validates the selected provider", async () => {
    const onSubmit = jest.fn();
    render(
      <Formik
        initialValues={newTseInitialValues}
        validationSchema={toFormikValidationSchema(NewTseSchema)}
        onSubmit={onSubmit}
      >
        {(formik) => (
          <Form>
            <TseForm {...formik} />
            <button type="submit">Save</button>
          </Form>
        )}
      </Formik>
    );

    fireEvent.change(screen.getByLabelText("tse.name"), { target: { value: "USB TSE" } });
    fireEvent.change(screen.getByLabelText("tse.serial"), { target: { value: "serial-123" } });
    fireEvent.change(screen.getByLabelText("tse.wsUrl"), { target: { value: "ws://tse.local" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ type: "diebold_nixdorf", serial: "serial-123" });
  });

  it("requires a Fiskaly profile when editing and submits without USB fields", async () => {
    const onSubmit = jest.fn();
    render(
      <Formik
        initialValues={{
          name: "Festival TSE",
          type: "fiskaly" as const,
          ws_url: "",
          ws_timeout: 5,
          password: "",
          fiskaly_profile: "",
        }}
        validationSchema={toFormikValidationSchema(UpdateTseSchema)}
        onSubmit={onSubmit}
      >
        {(formik) => (
          <Form>
            <UpdateTseForm {...formik} />
            <button type="submit">Save</button>
          </Form>
        )}
      </Formik>
    );

    expect(screen.getByLabelText("tse.fiskalyProfile")).toBeTruthy();
    expect(screen.queryByLabelText("tse.wsUrl")).toBeNull();
    expect(screen.queryByLabelText("tse.password")).toBeNull();

    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText("Required")).toBeTruthy();
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("tse.fiskalyProfile"), { target: { value: "festival-production" } });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      type: "fiskaly",
      fiskaly_profile: "festival-production",
    });
  });
});
