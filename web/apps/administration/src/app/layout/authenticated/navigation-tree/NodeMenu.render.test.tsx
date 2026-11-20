import { act, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
Object.assign(globalThis, { TextEncoder, TextDecoder });
const { createInstance } = require("i18next");
const { I18nextProvider, initReactI18next } = require("react-i18next");
const { MemoryRouter } = require("react-router-dom");
const { NodeMenu } = require("./NodeMenu");

test("shows authorized task links, marks nested routes active and updates labels when language changes", async () => {
  const i18n = createInstance();
  await i18n
    .use(initReactI18next)
    .init({
      lng: "en",
      resources: { en: { translation: { users: "Users" } }, de: { translation: { users: "Benutzer" } } },
      interpolation: { escapeValue: false },
    });
  const node = {
    id: 7,
    name: "Test",
    children: [],
    parent_ids: [],
    event: null,
    event_node_id: null,
    privileges_at_node: ["user_management"],
    computed_forbidden_objects_at_node: [],
  };
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={["/node/7/users/42"]}>
        <NodeMenu node={node} />
      </MemoryRouter>
    </I18nextProvider>
  );
  expect(screen.getByRole("link", { name: "Users" }).getAttribute("aria-current")).toBe("page");
  expect(screen.queryByRole("link", { name: "tills" })).toBeNull();
  await act(async () => {
    await i18n.changeLanguage("de");
  });
  expect(screen.getByRole("link", { name: "Benutzer" }).getAttribute("aria-current")).toBe("page");
});
