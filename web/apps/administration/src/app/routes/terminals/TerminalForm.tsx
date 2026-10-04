import { NewTerminal, selectEntryAreaAll, useListEntryAreasQuery, useListUserRolesQuery, useListCashRegistersAdminQuery, selectUserRoleAll, selectCashRegisterAll } from "@/api";
import { useCurrentNode } from "@/hooks";
import { FormCheckbox, FormSelect, FormTextField } from "@stustapay/form-components";
import { Select } from "@stustapay/components";
import { FormControl, InputLabel, MenuItem, Select as MuiSelect } from "@mui/material";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";
import * as React from "react";

export type TerminalFormProps<T extends NewTerminal> = FormikProps<T>;

export function TerminalForm<T extends NewTerminal>(props: TerminalFormProps<T>) {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { values, setFieldValue } = props;
  const { entryAreas } = useListEntryAreasQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        entryAreas: data ? selectEntryAreaAll(data) : [],
      }),
    }
  );

  const { data: roles } = useListUserRolesQuery({ nodeId: currentNode.id });
  const { data: registers } = useListCashRegistersAdminQuery({ nodeId: currentNode.id });
  const isDevice = values.login_mode === "device";
  const tillId = (values as NewTerminal & { till_id?: number | null }).till_id;

  React.useEffect(() => {
    if (values.mode === "till" && values.entry_area_id != null) {
      setFieldValue("entry_area_id", null);
    }
    if (values.mode !== "till" && values.self_service) {
      setFieldValue("self_service", false);
    }
    if (values.mode !== "till" || !values.self_service) {
      setFieldValue("app_display_mode", null);
    }
  }, [values.mode, values.entry_area_id, values.self_service, setFieldValue]);

  const showDisplayMode = values.mode === "till" && values.self_service;

  return (
    <>
      <FormControl fullWidth>
        <InputLabel id="terminal-login-mode-label">{t("terminal.loginMode.label")}</InputLabel>
        <MuiSelect
          labelId="terminal-login-mode-label"
          label={t("terminal.loginMode.label")}
          value={values.login_mode ?? "personal"}
          onChange={(event) => {
            setFieldValue("login_mode", event.target.value);
            if (event.target.value === "personal") {
              setFieldValue("device_role_id", null);
              setFieldValue("device_cash_register_id", null);
            }
          }}
        >
          <MenuItem value="personal">{t("terminal.loginMode.personal")}</MenuItem>
          <MenuItem value="device">{t("terminal.loginMode.device")}</MenuItem>
        </MuiSelect>
      </FormControl>
      {isDevice && (
        <>
          <Select
            multiple={false}
            options={roles ? selectUserRoleAll(roles) : []}
            value={roles?.entities[values.device_role_id ?? -1] ?? null}
            formatOption={(role) => role.name}
            label={t("terminal.deviceRole")}
            onChange={(role) => setFieldValue("device_role_id", role?.id ?? null)}
          />
          <Select
            multiple={false}
            options={registers ? selectCashRegisterAll(registers).filter(
              (register) => register.current_cashier_id == null || register.id === values.device_cash_register_id
            ) : []}
            value={registers?.entities[values.device_cash_register_id ?? -1] ?? null}
            formatOption={(register) => register.name}
            label={t("terminal.deviceCashRegister")}
            disabled={values.mode !== "till" || tillId == null}
            onChange={(register) => setFieldValue("device_cash_register_id", register?.id ?? null)}
          />
          <p>{t("terminal.deviceOperationHint")}</p>
        </>
      )}
      <FormTextField autoFocus name="name" label={t("common.name")} formik={props} />
      <FormTextField name="description" label={t("common.description")} formik={props} />
      <FormSelect
        name="mode"
        formik={props}
        multiple={false}
        formatOption={(mode: string) => t(`terminal.mode.${mode}`)}
        options={["till", "entry", "exit"]}
        label={t("terminal.mode.label")}
      />
      <Select
        multiple={false}
        formatOption={(area) => area.name}
        value={entryAreas.find((area) => area.id === values.entry_area_id) ?? null}
        options={entryAreas}
        label={t("entry.area")}
        disabled={values.mode === "till"}
        onChange={(area) => setFieldValue("entry_area_id", area?.id ?? null)}
      />
      <FormCheckbox
        name="self_service"
        label={t("terminal.selfService")}
        formik={props}
        disabled={values.mode !== "till"}
      />
      {showDisplayMode && (
        <FormControl fullWidth>
          <InputLabel id="terminal-app-display-mode-label">{t("terminal.appDisplayMode.label")}</InputLabel>
          <MuiSelect
            labelId="terminal-app-display-mode-label"
            label={t("terminal.appDisplayMode.label")}
            value={values.app_display_mode ?? ""}
            onChange={(event) => {
              const nextValue = event.target.value as "" | "day" | "night";
              setFieldValue("app_display_mode", nextValue === "" ? null : nextValue);
            }}
          >
            <MenuItem value="">{t("terminal.appDisplayMode.localDefault")}</MenuItem>
            <MenuItem value="day">{t("terminal.appDisplayMode.day")}</MenuItem>
            <MenuItem value="night">{t("terminal.appDisplayMode.night")}</MenuItem>
          </MuiSelect>
        </FormControl>
      )}
    </>
  );
}
