import { type Translations } from "../en/translations";

type NestedPartialAsStrings<T extends object> = {
  [Key in keyof T]?: T[Key] extends string ? string : T[Key] extends object ? NestedPartialAsStrings<T[Key]> : never;
};

export const translations: NestedPartialAsStrings<Translations> = {
    StuStaPay: "TeamFestlichPay",
    TeamFestlichPay: "TeamFestlichPay",
    cashiers: "Kassierer",
    advanced: "Fortgeschritten",
    accounts: "Konten",
    systemAccounts: "Systemkonten",
    findAccounts: "Konten finden",
    orders: "Bestellungen",
    submit: "Senden",
    download: "Herunterladen",
    products: "Produkte",
    tickets: "Tickets",
    actions: "Aktionen",
    add: "Hinzufügen",
    email: "E-Mail",
    edit: "Bearbeiten",
    delete: "Löschen",
    copy: "Kopieren",
    save: "Speichern",
    update: "Aktualisieren",
    logout: "Abmelden",
    login: "Anmelden",
    moneyOverview: "Übersicht",
    taxRates: "Steuersätze",
    users: "Benutzer",
    userRoles: "Benutzerrollen",
    confirm: "Bestätigen",
    cancel: "Abbrechen",
    tills: "Kassen",
    dsfinvk: "DSFinV-K",
    preview: "Vorschau",
    tillLayouts: "Kassenlayouts",
    tillButtons: "Kassentasten",
    tillProfiles: "Kassenprofile",
    registerStockings: "Kassenbestückungen",
    registers: "Registrierkassen",
    userToRoles: "Benutzer zu Rollen",
    languages: {
      en: "English",
      de: "Deutsch",
    },
    common: {
      id: "ID",
      definedAtNode: "Knoten",
      loadingError: "Fehler beim Laden der Seite",
      configLoadFailed: "Fehler beim Laden der Seitenkonfiguration: {{what}}",
    },
    nodes: {
      overview: "Übersicht",
      statistics: "Statistiken",
      settings: "Einstellungen",
    },
    account: {
      overview: "Übersicht",
      name: "Name",
      comment: "Kommentar",
      balance: "Saldo",
      type: "Typ",
      id: "ID",
      user_tag_uid: "Benutzerkennung UID",
      vouchers: "Gutscheine",
      changeBalance: "Saldo ändern",
      oldBalance: "Alter Saldo",
      newBalance: "Neuer Saldo",
      changeVoucherAmount: "Gutscheinbetrag ändern",
      oldVoucherAmount: "Alter Gutscheinbetrag",
      newVoucherAmount: "Neuer Gutscheinbetrag",
      changeTag: "Zugehöriges Tag ändern",
      oldTagUid: "UID des alten Tags",
      newTagUid: "UID des neuen Tags",
      disable: "Deaktivieren",
      disableSuccess: "Konto erfolgreich deaktiviert",
      findAccounts: "Konten finden",
      searchTerm: "Suchbegriff",
      history: {
        title: "Verlauf der Konto-Tag-Zuordnung",
        validUntil: "Gültig bis",
        account: "Konto",
        comment: "Kommentar",
      },
    },
    userTag: {
      userTags: "Benutzer-Tags",
      find: "Benutzer-Tags finden",
      searchTerm: "Suchbegriff",
      uid: "Benutzer-Tag UID",
      comment: "Kommentar",
      noAccount: "Kein Konto zugeordnet",
      account: "Konto",
      accountHistory: "Konto-Zuordnungshistorie",
    },
    auth: {
      username: "Benutzername",
      password: "Passwort",
      login: "Anmelden",
      loginFailed: "Anmeldung fehlgeschlagen: {{reason}}.",
      profile: "Profil",
      changePassword: "Passwort ändern",
      oldPassword: "Altes Passwort",
      newPassword: "Neues Passwort",
      confirmNewPassword: "Neues Passwort bestätigen",
      successfullyChangedPassword: "Passwort erfolgreich geändert",
      passwordsDontMatch: "Passwörter stimmen nicht überein",
      passwordChangeFailed: "Passwortänderung fehlgeschlagen: {{reason}}.",
    },
    cashier: {
      login: "Anmeldung",
      name: "Name",
      description: "Beschreibung",
      cashDrawerBalance: "Kassenbestand",
      tagId: "Tag-ID",
      till: "Kasse",
      shifts: "Schichten",
      closeOut: "Abschließen",
      showWithoutTill: "Ohne Kasse anzeigen",
      showZeroBalance: "Mit Nullsaldo anzeigen",
      notLoggedInAtTill: "Kassierer ist an keinem Terminal angemeldet",
      cashRegister: "Zugewiesene Registrierkasse",
      closeOuts: "Abschlüsse",
    },
    shift: {
      id: "ID",
      comment: "Kommentar",
      startedAt: "Begonnen am",
      endedAt: "Beendet am",
      actualCashDrawerBalance: "Tatsächlicher Kassenbestand wie gezählt",
      expectedCashDrawerBalance: "Erwarteter finaler Kassenbestand",
      cashDrawerImbalance: "Finaler Kassenbestandsunterschied",
      soldProductQuantity: "Menge",
    },
    closeOut: {
      start: "Start",
      warningStillLoggedInTitle: "Warnung",
      warningStillLoggedIn:
        "Der Kassierer ist noch an einem Terminal angemeldet, melden Sie ihn manuell ab, wenn möglich, andernfalls erzwingen Sie die Abmeldung an der Kasse selbst.",
      targetInDrawer: "Ziel im Geldschub",
      countedInDrawer: "Gezählt im Geldschub",
      difference: "Unterschied",
      comment: "Kommentar",
      closingOutUser: "Abschluss durch Finanzorga",
      sum: "Summe",
      coins: "Münzen",
      bill5Euro: "5€ *",
      bill10Euro: "10€ *",
      bill20Euro: "20€ *",
      bill50Euro: "50€ *",
      bill100Euro: "100€ *",
      bill200Euro: "200€ *",
    },
    order: {
      id: "ID",
      itemCount: "Anzahl der Artikel",
      lineItems: "Posten",
      status: "Status",
      paymentMethod: "Zahlungsmethode",
      customerAccountId: "Kundenkonto-ID",
      customerTagUid: "Kunden-Tag UID",
      bookedAt: "Gebucht am",
      type: "Typ",
      name: "Bestellung mit ID: {{id}}",
      totalPrice: "Gesamtpreis",
      totalTax: "Gesamtsteuer",
      totalNoTax: "Gesamtbetrag ohne Steuer",
      cancel: "Stornieren",
      confirmCancelOrderTitle: "Bestellung stornieren",
      confirmCancelOrderDescription: "Sind Sie sicher, dass Sie diese Bestellung stornieren möchten?",
      cancelSuccessful: "Bestellung erfolgreich storniert",
      cancelError: "Fehler beim Stornieren der Bestellung: {{what}}",
      editOrderInfo:
        "Das Bearbeiten einer Bestellung ist nur möglich, solange sie nicht storniert wurde. Nach der Bearbeitung wird die ursprüngliche Bestellung storniert und eine neue erstellt.",
    },
    item: {
      product: "Produkt",
      productPrice: "Produktpreis",
      quantity: "Menge",
      totalPrice: "Gesamtpreis",
      taxName: "Steuer",
      taxRate: "Steuersatz",
      totalTax: "Gesamtsteuer",
    },
    overview: {
      title: "Übersicht",
      fromTimestamp: "Von",
      toTimestamp: "Bis",
      mostSoldProducts: "Meistverkaufte Produkte",
      showDetails: "Details anzeigen",
      quantitySold: "# Verkauft",
      selectedTill: "Kasse",
      statsByTill: "Produkte verkauft nach Kasse",
      depositBalance: "Pfandbilanz",
      hideDeposits: "Pfand verstecken",
      voucherStats: "Gutscheine",
      vouchersIssued: "Ausgestellt",
      vouchersSpent: "Eingelöst",
    },
    ticket: {
      name: "Name",
      product: "Produkt",
      price: "Preis",
      isLocked: "Gesperrt",
      lock: "Ticket sperren",
      taxRate: "Steuersatz",
      totalPrice: "Gesamtpreis",
      initialTopUpAmount: "Erstaufladungsbetrag",
      restriction: "Einschränkung",
      create: "Neues Ticket hinzufügen",
      update: "Ticket aktualisieren",
      delete: "Ticket löschen",
      deleteDescription: "Ticketlöschung bestätigen",
    },
    product: {
      name: "Name",
      price: "Preis",
      priceInVouchers: "Preis in Gutscheinen",
      restrictions: "Einschränkungen",
      isLocked: "Gesperrt",
      isReturnable: "Kann zurückgegeben werden",
      isFixedPrice: "Festpreis",
      taxRate: "Steuersatz",
      fixedPrice: "Preis ist festgelegt",
      lock: "Produkt sperren",
      create: "Neues Produkt hinzufügen",
      update: "Produkt aktualisieren",
      delete: "Produkt löschen",
      deleteDescription: "Produktlöschung bestätigen",
    },
    sumup: {
      sumup: "SumUp",
      checkouts: "SumUp Kassen",
      transactions: "Transaktionen",
      transaction: {
        product_summary: "Zusammenfassung",
        card_type: "Kartentyp",
        type: "Typ",
      },
      checkout: {
        reference: "Kassenreferenz",
        amount: "Betrag",
        payment_type: "Zahlungsart",
        status: "Status",
        date: "Datum",
      },
    },
    settings: {
      title: "Einstellungen",
      language: "Sprache",
      updateEventSucessful: "Ereignis erfolgreich aktualisiert",
      updateEventFailed: "Aktualisierung des Ereignisses fehlgeschlagen: {{reason}}.",
      juristiction: "Gerichtsbarkeit",
      serverSideConfig: "Serverseitige Einstellungen",
      localConfig: "Lokale Einstellungen",
      createEvent: {
        link: "Neues Ereignis erstellen",
        heading: "Neues Ereignis unten erstellen {{parentNodeName}}",
      },
      createNode: {
        link: "Neuen Knoten erstellen",
        heading: "Neuen Knoten unten erstellen {{parentNodeName}}",
      },
      general: {
        tabLabel: "Allgemein",
        name: "Name",
        description: "Beschreibung",
        forbidden_objects_at_node: "Verbotene Objekte am Knoten",
        forbidden_objects_in_subtree: "Verbotene Objekte im Unterbaum",
        ust_id: "UST-ID",
        max_account_balance: "Maximaler Kontostand",
        currency_identifier: "Währungskennung",
        start_date: "Startdatum",
        end_date: "Enddatum",
        daily_end_time: "Tägliche Endzeit",
        start_end_date_must_be_set_same: "Start- und Enddatum müssen beide gesetzt oder nicht gesetzt werden",
      },
      customerPortal: {
        tabLabel: "Kundenportal",
        baseUrl: "Basis-URL des Kundenportals",
        contact_email: "Kontakt-E-Mail",
        data_privacy_url: "Datenschutz-URL",
        about_page_url: "Über uns-URL",
      },
      agb: {
        tabLabel: "AGB",
        preview: "Vorschau anzeigen",
        content: "AGB (im Markdown-Format)",
      },
      faq: {
        tabLabel: "FAQ",
        preview: "Vorschau anzeigen",
        content: "FAQ (im Markdown-Format)",
      },
      bon: {
        tabLabel: "Bon",
        issuer: "Bon-Aussteller",
        address: "Bon-Adresse",
        title: "Bon-Titel",
        previewBon: "Bon-Vorschau",
      },
      sumup: {
        tabLabel: "SumUp",
        sumup_payment_enabled: "SumUp-Zahlung aktiviert",
        sumup_topup_enabled: "SumUp-Aufladung aktiviert",
        sumup_api_key: "SumUp-API-Schlüssel",
        sumup_merchant_code: "SumUp-Händlercode",
        sumup_affiliate_key: "SumUp-Affiliate-Schlüssel",
      },
      payout: {
        tabLabel: "Auszahlung",
        sepa_enabled: "Auszahlung aktiviert",
        ibanNotValid: "IBAN ist nicht gültig",
        sepa_sender_name: "SEPA-Absendername",
        sepa_sender_iban: "SEPA-Absender-IBAN",
        sepa_description: "SEPA-Beschreibung",
        sepa_allowed_country_codes: "Erlaubte Ländercodes für Auszahlungen",
      },
      email: {
        tabLabel: "E-Mail",
      },
      settingsUpdateError: "Fehler beim Aktualisieren der Einstellung: {{what}}",
      theme: {
        title: "Thema",
        browser: "Browser",
        dark: "Dunkel",
        light: "Hell",
      },
    },
    taxRateName: "Name",
    taxRateRate: "Satz",
    taxRateDescription: "Beschreibung",
    createTaxRate: "Neuen Steuersatz hinzufügen",
    updateTaxRate: "Steuersatz aktualisieren",
    deleteTaxRate: "Steuersatz löschen",
    deleteTaxRateDescription: "Steuersatzlöschung bestätigen",
    till: {
      till: "Kasse",
      tills: "Kassen",
      id: "ID",
      name: "Name",
      profile: "Profil",
      description: "Beschreibung",
      registrationUUID: "Registrierungs-ID",
      loggedIn: "Terminal registriert",
      logout: "Kasse abmelden",
      cashRegisterBalance: "Aktueller Kassenbestand",
      cashRegisterName: "Aktueller Kassenname",
      create: "Neue Kasse hinzufügen",
      update: "Kasse aktualisieren",
      delete: "Kasse löschen",
      deleteDescription: "Kassenlöschung bestätigen",
      activeUser: "Angemeldeter Benutzer",
      tseId: "TSE-ID",
      tseSerial: "TSE-Seriennummer",
      forceLogoutUser: "Benutzer erzwingen abmelden",
      forceLogoutUserDescription:
        "Benutzer am Terminal erzwingen abmelden. Dies sollte NIEMALS gemacht werden, während ein Kassierer das Terminal noch verwendet",
      unregisterTill: "Terminal erzwingen abmelden",
      unregisterTillDescription:
        "Ein Terminal erzwingen abmelden. Dies sollte NIEMALS gemacht werden, während ein Kassierer das Terminal noch verwendet",
    },
    layout: {
      layout: "Layout",
      layouts: "Layouts",
      buttons: "Tasten",
      tickets: "Tickets",
      name: "Name",
      description: "Beschreibung",
      create: "Neues Layout hinzufügen",
      update: "Layout aktualisieren",
      delete: "Layout löschen",
      deleteDescription: "Layoutlöschung bestätigen",
    },
    profile: {
      profile: "Profil",
      profiles: "Profile",
      name: "Name",
      description: "Beschreibung",
      create: "Neues Profil hinzufügen",
      allowTopUp: "Aufladung erlauben",
      allowCashOut: "Auszahlung erlauben",
      allowTicketSale: "Ticketverkauf erlauben",
      allowedUserRoles: "Erlaubte Benutzerrollen",
      layout: "Layout",
      update: "Profil aktualisieren",
      delete: "Profil löschen",
      deleteDescription: "Profillöschung bestätigen",
    },
    button: {
      button: "Taste",
      buttons: "Tasten",
      create: "Neue Taste hinzufügen",
      update: "Taste aktualisieren",
      delete: "Taste löschen",
      deleteDescription: "Tastenlöschung bestätigen",
      availableButtons: "Verfügbare Tasten",
      assignedButtons: "Zugewiesene Tasten",
      name: "Name",
      price: "Preis",
      addProductToButton: "Ein Produkt hinzufügen",
    },
    register: {
      stockings: "Kassenbestückungen",
      createStocking: "Neue Kassenbestückungsvorlage hinzufügen",
      updateStocking: "Kassenbestückungsvorlage aktualisieren",
      deleteStocking: "Kassenbestückungsvorlage aktualisieren",
      deleteStockingDescription: "Kassenbestückungslöschung bestätigen",
      createRegister: "Neue Registrierkasse hinzufügen",
      updateRegister: "Registrierkasse aktualisieren",
      deleteRegister: "Registrierkasse aktualisieren",
      deleteRegisterDescription: "Registrierkassenlöschung bestätigen",
      registers: "Registrierkassen",
      currentBalance: "Saldo",
      currentCashier: "Kassierer",
      currentTill: "Kasse",
      update: "Registrierkasse aktualisieren",
      name: "Name",
      transfer: "An einen anderen Kassierer übertragen",
      transferTargetCashier: "Kassierer, an den die Kasse übertragen werden soll",
      cannotTransferNotAssigned:
        "Diese Registrierkasse ist keinem Kassierer zugewiesen, daher können wir sie nicht an einen anderen übertragen. Bitte verwenden Sie die Funktion zum Auffüllen des Kassierers dafür.",
      euro200: "Anzahl der 200€-Scheine",
      euro100: "Anzahl der 100€-Scheine",
      euro50: "Anzahl der 50€-Scheine",
      euro20: "Anzahl der 20€-Scheine",
      euro10: "Anzahl der 10€-Scheine",
      euro5: "Anzahl der 5€-Scheine",
      euro2: "Anzahl der 2€-Rollen, eine Rolle = 25 Stk. = 50€",
      euro1: "Anzahl der 1€-Rollen, eine Rolle = 25 Stk. = 25€",
      cent50: "Anzahl der 50-Cent-Rollen, eine Rolle = 40 Stk. = 20€",
      cent20: "Anzahl der 20-Cent-Rollen, eine Rolle = 40 Stk. = 8€",
      cent10: "Anzahl der 10-Cent-Rollen, eine Rolle = 40 Stk. = 4€",
      cent5: "Anzahl der 5-Cent-Rollen, eine Rolle = 50 Stk. = 2,50€",
      cent2: "Anzahl der 2-Cent-Rollen, eine Rolle = 50 Stk. = 1€",
      cent1: "Anzahl der 1-Cent-Rollen, eine Rolle = 50 Stk. = 0,50€",
      variableInEuro: "Zusätzliche variable Bestückung in Euro",
      stockingTotal: "Gesamt",
    },
    createUser: "Benutzer erstellen",
    updateUser: "Benutzer aktualisieren",
    userLogin: "Anmeldung",
    userDisplayName: "Anzeigename",
    userPassword: "Passwort",
    userDescription: "Beschreibung",
    userPrivileges: "Privilegien",
    userCreateError: "Fehler beim Erstellen des Benutzers: {{what}}",
    userUpdateError: "Fehler beim Aktualisieren des Benutzers: {{what}}",
    deleteUser: "Benutzer löschen",
    deleteUserDescription: "Benutzerlöschung bestätigen",
    user: {
      user: "Benutzer",
      users: "Benutzer",
      roles: "Rollen",
      login: "Anmeldung",
      displayName: "Anzeigename",
      description: "Beschreibung",
      tagUid: "Benutzer-Tag UID",
      noTagAssigned: "Kein Tag zugewiesen",
      changePassword: {
        title: "Passwort ändern",
        new_password: "Neues Passwort",
        new_password_confirm: "Neues Passwort bestätigen",
      },
    },
    userRole: {
      name: "Name",
      create: "Neue Benutzerrolle erstellen",
      update: "Benutzerrolle aktualisieren",
      isPrivileged: "Ist privilegiert",
      createError: "Fehler beim Erstellen der Benutzerrolle: {{what}}",
      updateError: "Fehler beim Aktualisieren der Benutzerrolle: {{what}}",
      privileges: "Privilegien",
      delete: "Benutzerrolle löschen",
      deleteDescription: "Benutzerrollenlöschung bestätigen",
    },
    userToRole: {
      user: "Benutzer",
      role: "Rolle",
      create: "Einen Benutzer einer Rolle für Knoten {{node}} zuordnen",
      deleteAssociation: "Rollenzuordnung entfernen",
      deleteAssociationDescription: "Zuordnung entfernen",
    },
    tse: {
      tses: "TSE",
      name: "Name",
      type: "Typ",
      status: "Status",
      serial: "Seriennummer",
      create: "Eine neue TSE erstellen",
      wsUrl: "Websocket-URL",
      wsTimeout: "Websocket-Timeout in Sekunden",
      password: "TSE-Passwort",
      hashalgo: "Hash-Algorithmus",
      timeFormat: "Zeitformat",
      publicKey: "Öffentlicher Schlüssel",
      certificate: "Zertifikat",
      processDataEncoding: "Datenkodierung",
    },
    payoutRun: {
      id: "ID",
      pendingPayoutDetails: "Übersicht über Kunden, denen kein Auszahlungslauf zugewiesen ist",
      maxPayoutSum: "Maximaler Auszahlungsbetrag in diesem Auszahlungslauf",
      downloadCsv: "CSV",
      downloadSepa: "SEPA",
      downloadSepaModalTitle: "SEPA XML herunterladen",
      batchSize: "Stapelgröße",
      create: "Einen neuen Auszahlungslauf erstellen",
      createdAt: "Erstellt am",
      createdBy: "Erstellt von",
      executionDate: "Ausführungsdatum",
      totalPayoutAmount: "Gesamtauszahlungsbetrag",
      totalDonationAmount: "Gesamtspendenbetrag",
      nPayouts: "Anz. Auszahlungen",
      payoutRuns: "Auszahlungsläufe",
      payoutsInPayoutRun: "Kunden, die in diesem Auszahlungslauf ausgezahlt werden",
      payout: {
        id: "Konto-ID",
      },
    },
    customer: {
      bankAccountHolder: "Kontoinhaber",
    },
} as const;

export default translations;
