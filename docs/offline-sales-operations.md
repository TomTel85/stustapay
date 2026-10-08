# Offline-Notbetrieb an POS-Kassen

Der Offline-Notbetrieb erlaubt vorbereiteten Android-Kassen, bei einem Ausfall der Serververbindung begrenzte Verkäufe mit Kundenbändchen anzunehmen. Die Funktion ist je Veranstaltung standardmäßig deaktiviert.

## Vor der Veranstaltung

Aktiviere den Notbetrieb in der Administration unter **Veranstaltung → Einstellungen → Offline-Verkäufe**. Prüfe die Gültigkeitsdauer und die Limits für Verkäufe und Pfandrückgaben. Die Voreinstellungen sind zwei Stunden, 20 € je Vorgang, 30 € je Bändchen und Kasse sowie 500 € je Kasse. Die Pfandrückgabelimits haben dieselben Voreinstellungen. Ein Limit von 0 € sperrt die entsprechende Buchungsart.

Die Kasse muss online angemeldet und vollständig vorbereitet worden sein. Bereite sie nach Änderungen an Preisen oder Einstellungen erneut vor. Die zuletzt vorbereitete Berechtigung ist zeitlich begrenzt.

## Während eines Ausfalls

Die Kasse zeigt an, wenn sie offline arbeitet. Verkäufe, die innerhalb des vorbereiteten Kundenbestands und der Limits liegen, werden lokal gespeichert und dem Kunden als offline angenommen angezeigt. Behalte die Anzeige im Blick und nutze die Kasse nur weiter, solange ihre Vorbereitung gültig ist. Noch nicht abgeglichene Pfandgutschriften stehen nicht für weitere Einkäufe zur Verfügung.

Die Limits verringern das Risiko, verhindern aber nicht, dass dasselbe Guthaben an mehreren getrennten Kassen ausgegeben wird. Kassen teilen ihre Offline-Ausgabenbudgets nicht miteinander.

Verkaufsgrenzen zählen die positiven Positionen vor der Pfandverrechnung; Rückgaben verbrauchen ein separates Budget. Offline sind vorbereitete Festpreisartikel und einzelne Artikel mit freiem Preis (einschließlich Trinkgeld) nutzbar. Freie Preise müssen nichtnegative Beträge mit höchstens zwei Nachkommastellen sein; sie zählen vollständig zu den Verkaufslimits und benötigen verfügbares Guthaben. Kassentasten, die mehrere Produkte zu einem freien Preis bündeln, und freie Pfandrückgabepreise werden nicht unterstützt. Festpreisartikel und Trinkgeld können gemeinsam in einem Warenkorb gebucht werden. Gutscheine, Aufladungen, Auszahlungen, Bar- und Kartenzahlungen, Stornos und Bändchenwechsel benötigen weiterhin den Server. Ein Bedienerwechsel ist offline nicht möglich; Abmelden beendet die lokale Berechtigung. Ein Neustart erhält gespeicherte Buchungen und Limits, verlängert aber nicht die Gültigkeit.

## Nach Wiederverbindung

Die Kasse überträgt ihre gespeicherten Verkäufe automatisch. Prüfe in der Veranstaltungsübersicht den Status der gemeldeten Offline-Verkäufe, Kontostände nach Import und den letzten Kontakt der vorbereiteten Kassen. Klärfälle müssen geprüft werden.

Schließe einen Klärfall nur, nachdem der Verkauf manuell abgeglichen wurde. Das Schließen wird protokolliert und gibt die betroffene Kasse frei; es erzeugt selbst keine finanzielle Buchung. Verkäufe, die das verbleibende Guthaben überschreiten, können als Kundenschuld enden.

Eine kurze Wiederverbindung setzt die Limits nicht zurück. Dafür müssen die offenen Buchungen abgeglichen beziehungsweise geklärt und ein neuer vollständiger Datenstand geladen sein. Lösche keine App-Daten und setze kein Gerät zurück, solange es offene Buchungen enthält: Nicht übertragene Verkäufe existieren nur auf diesem Gerät.

## Upgrade und Freigabe

Installiere zuerst das Backend mit Migration 61, dann die Administration und anschließend die Android-App. Die Funktion bleibt bis zum erfolgreichen Pilotbetrieb deaktiviert. Prüfe mit zwei Kassen WLAN-Ausfall, Wiederverbindung, Neustart, NFC, Kundenanzeige, Pfandrückgaben, Überziehungen sowie die bestehenden Beleg- und TSE-Abläufe.

Eine alte, noch offene Verkaufsbuchung wird unter ihrer ursprünglichen Buchungs-ID übernommen. Die alte Speicherung enthielt keinen Bediener: Ist die Buchung noch nicht auf dem Server angekommen, muss ein online angemeldeter Bediener die Wiederholung ausdrücklich übernehmen. Bei alten bereits gebuchten Verkäufen mit Gutscheinen reicht der gespeicherte Inhalt nicht zur sicheren Rekonstruktion; diese Fälle müssen manuell geprüft werden. Wiederholungen erzeugen keine neue Buchungs-ID.
