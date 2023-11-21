import { NewTill } from "@/api";
import { FormTextField } from "@stustapay/form-components";
import { FormikProps } from "formik";
import { useTranslation } from "react-i18next";
import { TillProfile, selectTillProfileAll, useListTillProfilesQuery } from "@/api";
import { Tse, selectTseAll, useListTsesQuery } from "@/api";
import { useCurrentNode } from "@/hooks";
import { Select } from "@stustapay/components";


export type TillFormProps<T extends NewTill> = FormikProps<T>;

export function TillForm<T extends NewTill>(props: TillFormProps<T>) {
  const { currentNode } = useCurrentNode();
  const { touched, values, setFieldValue, errors } = props;
  const { t } = useTranslation();
  const { profiles } = useListTillProfilesQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        profiles: data ? selectTillProfileAll(data) : [],
      }),
    }
  );
  const { tses } = useListTsesQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        tses: data ? selectTseAll(data) : [],
      }),
    }
  );        
  return (
    <>
      <FormTextField autoFocus name="name" label={t("till.name")} formik={props} />
      <FormTextField name="description" label={t("till.description")} formik={props} />
      <Select
        multiple={false}
        formatOption={(profile: TillProfile) => profile.name}
        value={profiles.find((p) => p.id === values.active_profile_id) ?? null}
        options={profiles}
        label={t("till.profile")}
        error={touched.active_profile_id && !!errors.active_profile_id}
        helperText={(touched.active_profile_id && errors.active_profile_id) as string}
        onChange={(value: TillProfile | null) =>
          value != null ? setFieldValue("active_profile_id", value.id) : undefined
        }
      />
      <Select
        multiple={false}
        formatOption={(tse: Tse) => tse.name}
        value={tses.find((t) => t.id === values.active_tse_id) ?? null}
        options={tses}
        label={t("till.tse")}
        error={touched.active_tse_id && !!errors.active_tse_id}
        helperText={(touched.active_tse_id && errors.active_tse_id) as string}
        onChange={(value: Tse | null) =>
          value != null ? setFieldValue("active_tse_id", value.id) : undefined
        }
      />
    </>
    );
}
