import { type Translations } from "../en/translations";

type NestedPartialAsStrings<T extends object> = {
  [Key in keyof T]?: T[Key] extends string ? string : T[Key] extends object ? NestedPartialAsStrings<T[Key]> : never;
};

export const translations: NestedPartialAsStrings<Translations> = {
  StuStaPay: "TeamFestlichPay",
  TeamFestlichPay: "TeamFestlichPay",
  logout: "Logout",
  login: "Login",
  userTagUid: "Guthabenkarte-Chip ID",
  userTagPin: "Guthabenkarte-Chip Pin",
  loginFailed: "Login fehlgeschlagen: {{reason}}.",
  errorLoadingCustomer: "Fehler beim Laden der Kundendaten",
  payoutInfo:
    "Um dein Restguthaben nach dem Festival zu erhalten, <1>trage bitte deine Bankdaten hier ein</1>. Die erste Auszahlung findet voraussichtlich 3 Wochen nach Veranstaltungsende statt.",
  about: "Impressum",
  contact: "Kontakt",
  wristbandTagExample: "Beispiel einer Guthabenkarte",
  wristbandTagExampleTitle: "Guthabenkarte-Chip Beispiel mit PIN und ID",
  wristbandTagExampleDescription:
    "Die Chip ID und PIN findest Du auf der Rückseite deiner Guthabenkarte.",
  termsAndConditionsHeader: "Die Datenschutzbestimmungen können <1>hier</1> eingesehen werden.",
  privacyPolicyHeader: "Unsere AGBs können <1>hier</1> eingesehen werden.",
  languages: {
    en: "English",
    de: "Deutsch",
  },
  nav: {
    payout: "Auszahlung",
    topup: "Aufladung",
    agb: "AGB",
    faq: "FAQ",
  },
  balance: "Guthaben",
  tagUid: "Guthabenkarte-Chip ID",
  vouchers: "Getränkemarken",
  order: {
    loadingError: "Fehler beim laden der Bestellungen",
    productName: "Produktname",
    productPrice: "Produktpreis",
    quantity: "Menge",
    total: "Summe",
    viewReceipt: "Beleg anzeigen",
    bookedAt: "Gebucht um: {{date}}",
    orderType: {
      sale: "Kauf",
      cancel_sale: "Stornierter Kauf",
      top_up: "Aufladung",
      pay_out: "Auszahlung",
      ticket: "Ticketkauf",
    },
  },
  payout: {
    iban: "IBAN",
    bankAccountHolder: "Kontoinhaber",
    email: "E-Mail",
    info: "Damit wir dein Restguthaben überweisen können, trage bitte deine Bankdaten hier ein. Du kannst auch einen Teil oder Dein gesamtes Guthaben an uns spenden, um unser ehrenamtliches Engagement zu unterstützen. Die erste Auszahlung findet voraussichtlich 3 Wochen nach Veranstaltungsende statt.",
    ibanNotValid: "ungültige IBAN",
    countryCodeNotSupported: "IBAN Ländercode wird nicht unterstützt",
    mustAcceptPrivacyPolicy: "Sie müssen die Datenschutserklärung akzeptieren",
    privacyPolicyCheck: "Ich habe die <1>Datenschutzerklärung</1> gelesen und akzeptiere sie.",
    errorFetchingData: "Fehler beim laden der Daten.",
    updatedBankData:
      "Bankdaten erfolgreich aktualisiert. Die erste Auszahlung erfolgt voraussichtlich 3 Wochen nach Festivalende.",
    errorWhileUpdatingBankData: "Fehler beim aktualisieren der Bankdaten.",
    donationMustBePositive: "Das Spende muss positiv sein",
    donationExceedsBalance: "Die Spende darf nicht den Kontostand überschreiten",
    donationTitle: "Spende",
    payoutTitle: "Auszahlung",
    donationAmount: "Spendebetrag ",
    payoutAmount: "Auszahlungsbetrag ",
    donationDescription:
      "Hat dir die Veranstaltung gefallen? Wir würden uns über eine Spende freuen, um unsere ehrenamtliche Arbeit zu unterstützen.",
    donateRemainingBalanceOf: "Spende verbleibende Summe von ",
    submitPayoutData: "Bankdaten speichern",
  },
  topup: {
    onlineTopUp: "Online-Aufladung",
    description: "Du kannst dein Festival-Guthaben hier mit Kreditkarte aufladen.",
    amount: "Betrag",
    errorWhileCreatingCheckout: "Fehler beim erstellen der SumUp-Zahlung.",
    errorAmountGreaterZero: "Betrag muss größer als 0 sein.",
    errorAmountMustBeIntegral: "Centbeträge sind nicht erlaubt.",
    sumupTopupDisabled: "Online-Aufladung ist deaktiviert.",
    tryAgain: "Versuche es noch einmal",
    success: {
      title: "Aufladung erfolgreich",
      message: "Bitte gehe weiter zur <1>Übersichtsseite</1>.",
    },
    error: {
      title: "Aufladung fehlgeschlagen",
      message: "Ein unbekannter Fehler ist aufgetreten.",
    },
  },
} as const;

export default translations;
