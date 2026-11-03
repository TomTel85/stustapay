import * as React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
jest.mock("@stustapay/components", () => {
  global.TextEncoder = require("util").TextEncoder;
  return jest.requireActual("@stustapay/components");
});

const mockNavigate = jest.fn();
const mockCurrentNode = { id: 1 };
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }));

const mockCreateProduct = jest.fn();
const mockCreateButton = jest.fn();
jest.mock("@/api", () => ({
  useCreateProductMutation: () => [mockCreateProduct],
  useCreateTillButtonMutation: () => [mockCreateButton],
  useListProductsQuery: () => ({
    data: {
      ids: [5, 6],
      entities: {
        5: { id: 5, name: "Cup deposit", price: 2, is_returnable: true },
        6: { id: 6, name: "Water", price: 1, is_returnable: false },
      },
    },
  }),
  selectProductAll: (data: { entities: Record<string, unknown> }) => Object.values(data.entities),
}));
jest.mock("@/app/layout", () => ({ withPrivilegeGuard: (_: string, component: unknown) => component }));
jest.mock("@/app/routes", () => ({ ProductRoutes: { list: () => "/products" } }));
jest.mock("@/hooks", () => ({
  useCurrentNode: () => ({ currentNode: mockCurrentNode }),
  useCurrencyFormatter: () => (value: number) => `EUR ${value.toFixed(2)}`,
}));
jest.mock("@/components", () => ({ CreateLayout: require("@/components/layouts/CreateLayout").CreateLayout }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
jest.mock("./ProductForm", () => ({
  ProductForm: (props: { values: { name: string }; setFieldValue: (key: string, value: unknown) => void }) => (
    <input
      aria-label="Name"
      value={props.values.name}
      onChange={(event) => {
        props.setFieldValue("name", event.target.value);
        props.setFieldValue("tax_rate_id", 1);
      }}
    />
  ),
}));

const { ProductCreate } = require("./ProductCreate");

function setup() {
  render(<ProductCreate />);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Beer" } });
}

beforeEach(() => {
  mockCurrentNode.id = 1;
  jest.clearAllMocks();
  mockCreateProduct.mockReturnValue({ unwrap: () => Promise.resolve({ id: 10, name: "Beer" }) });
  mockCreateButton.mockReturnValue({ unwrap: () => Promise.resolve({ name: "Beer" }) });
});

test("creates a button with the product name by default", async () => {
  setup();
  expect((screen.getByLabelText("product.createButton") as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/products"));
  expect(mockCreateButton).toHaveBeenCalledWith({ nodeId: 1, newTillButton: { name: "Beer", product_ids: [10] } });
  expect(mockCreateProduct.mock.calls[0][0].newProduct).not.toHaveProperty("create_button");
});

test("allows creating only the product", async () => {
  setup();
  fireEvent.click(screen.getByLabelText("product.createButton"));
  expect(screen.queryByLabelText("product.depositProduct")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/products"));
  expect(mockCreateButton).not.toHaveBeenCalled();
});

test("offers only returnable products and includes the selected deposit on the button", async () => {
  setup();
  fireEvent.mouseDown(screen.getByRole("combobox"));
  expect(screen.queryByRole("option", { name: /Water/ })).toBeNull();
  fireEvent.click(screen.getByRole("option", { name: /Cup deposit/ }));
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/products"));
  expect(mockCreateButton).toHaveBeenCalledWith({ nodeId: 1, newTillButton: { name: "Beer", product_ids: [10, 5] } });
});

test("retries only the button after a button failure and locks the saved product", async () => {
  jest.spyOn(console, "warn").mockImplementation(() => undefined);
  mockCreateButton.mockReturnValueOnce({ unwrap: () => Promise.reject(new Error("Unavailable")) });
  setup();
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await screen.findByText("product.buttonCreationFailed");
  expect((screen.getByLabelText("Name") as HTMLInputElement).closest("fieldset")?.disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/products"));
  expect(mockCreateProduct).toHaveBeenCalledTimes(1);
  expect(mockCreateButton).toHaveBeenCalledTimes(2);
  jest.restoreAllMocks();
});

test("does not create a button if saving the product fails", async () => {
  jest.spyOn(console, "warn").mockImplementation(() => undefined);
  mockCreateProduct.mockReturnValueOnce({ unwrap: () => Promise.reject(new Error("Unavailable")) });
  setup();
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await waitFor(() => expect(mockCreateProduct).toHaveBeenCalledTimes(1));
  await waitFor(() => expect((screen.getByRole("button", { name: "add" }) as HTMLButtonElement).disabled).toBe(false));
  expect(mockCreateButton).not.toHaveBeenCalled();
  expect(screen.queryByText("Product list")).toBeNull();
  jest.restoreAllMocks();
});

test("can finish without a button after button creation failed", async () => {
  jest.spyOn(console, "warn").mockImplementation(() => undefined);
  mockCreateButton.mockReturnValueOnce({ unwrap: () => Promise.reject(new Error("Unavailable")) });
  setup();
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await screen.findByText("product.buttonCreationFailed");
  fireEvent.click(screen.getByLabelText("product.createButton"));
  fireEvent.click(screen.getByRole("button", { name: "add" }));
  await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/products"));
  expect(mockCreateProduct).toHaveBeenCalledTimes(1);
  expect(mockCreateButton).toHaveBeenCalledTimes(1);
  jest.restoreAllMocks();
});

test("creates a fresh product after a previous node's pending request completes", async () => {
  const warning = jest.spyOn(console, "warn").mockImplementation(() => undefined);
  let resolveProduct!: (product: { id: number; name: string }) => void;
  const pendingProduct = new Promise((resolve) => {
    resolveProduct = resolve;
  });
  mockCreateProduct.mockReturnValueOnce({ unwrap: () => pendingProduct });
  mockCreateButton.mockReturnValueOnce({ unwrap: () => Promise.reject(new Error("Unavailable")) });
  try {
    const view = render(<ProductCreate />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Beer" } });
    fireEvent.click(screen.getByRole("button", { name: "add" }));
    await waitFor(() => expect(mockCreateProduct).toHaveBeenCalledTimes(1));

    mockCurrentNode.id = 2;
    view.rerender(<ProductCreate />);
    await act(async () => resolveProduct({ id: 10, name: "Beer" }));
    await waitFor(() => expect(mockCreateButton).toHaveBeenCalledTimes(1));

    mockCreateProduct.mockReturnValueOnce({ unwrap: () => Promise.resolve({ id: 20, name: "Wine" }) });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Wine" } });
    fireEvent.click(screen.getByRole("button", { name: "add" }));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/products"));
    expect(mockCreateProduct).toHaveBeenLastCalledWith({
      nodeId: 2,
      newProduct: expect.objectContaining({ name: "Wine" }),
    });
    expect(mockCreateButton).toHaveBeenLastCalledWith({
      nodeId: 2,
      newTillButton: { name: "Wine", product_ids: [20] },
    });
  } finally {
    warning.mockRestore();
  }
});
