import { config, fetchConfig } from "./common";

jest.mock("@/store", () => ({ selectAuthToken: jest.fn() }));

const validConfig = {
  node_id: 7,
  currency_identifier: "EUR",
  translation_texts: { "de-DE": { faq: "Globale Fragen" } },
};

describe("customer portal configuration bootstrap", () => {
  const originalFetch = global.fetch;
  const mockFetch = jest.fn();

  beforeEach(() => {
    mockFetch.mockReset();
    global.fetch = mockFetch;
  });

  afterAll(() => {
    global.fetch = originalFetch;
  });

  test("loads the event configuration and localized FAQ", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => validConfig });
    const result = await fetchConfig();
    expect(result.apiConfig).toEqual(validConfig);
    expect(mockFetch).toHaveBeenCalledWith(
      `${window.location.origin}/api/config?base_url=${encodeURIComponent(window.location.origin)}`
    );
  });

  test.each([400, 500])("rejects HTTP %s instead of publishing an error response as configuration", async (status) => {
    await fetchConfigWithValidResponse();
    const previousConfig = config;
    const json = jest.fn().mockResolvedValue({ message: "Invalid customer portal configuration" });
    mockFetch.mockResolvedValue({ ok: false, status, json });
    await expect(fetchConfig()).rejects.toThrow(`configuration request failed (${status})`);
    expect(json).not.toHaveBeenCalled();
    expect(config).toBe(previousConfig);
  });

  test.each([
    { ...validConfig, translation_texts: undefined },
    { ...validConfig, translation_texts: null },
    { ...validConfig, translation_texts: { "de-DE": "not a translation map" } },
    { message: "Invalid customer portal configuration" },
  ])("rejects malformed successful configuration responses", async (payload) => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => payload });
    await expect(fetchConfig()).rejects.toThrow();
  });

  test("accepts empty translation texts", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ ...validConfig, translation_texts: {} }) });
    expect((await fetchConfig()).apiConfig.translation_texts).toEqual({});
  });

  async function fetchConfigWithValidResponse() {
    mockFetch.mockResolvedValue({ ok: true, json: async () => validConfig });
    await fetchConfig();
  }
});
