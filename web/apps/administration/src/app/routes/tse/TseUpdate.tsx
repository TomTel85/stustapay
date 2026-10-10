import { selectTseById, useListTsesQuery, useUpdateTseMutation } from "@/api";
import { TseRoutes } from "@/app/routes";
import { EditLayout } from "@/components";
import { useCurrentNode } from "@/hooks";
import { Loading } from "@stustapay/components";
import { TseType, UpdateTse, UpdateTseSchema } from "@stustapay/models";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useParams } from "react-router-dom";
import { UpdateTseForm } from "./UpdateTseForm";

export const TseUpdate: React.FC = () => {
  const { t } = useTranslation();
  const { tseId } = useParams();
  const { currentNode } = useCurrentNode();
  const { tse, isLoading, error } = useListTsesQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        tse: data ? selectTseById(data, Number(tseId)) : undefined,
      }),
    }
  );
  const [updateTse] = useUpdateTseMutation();

  if (isLoading || !tse) {
    return <Loading />;
  }

  if (error) {
    return <Navigate to={TseRoutes.list()} />;
  }

  const initialValues: UpdateTse = {
    name: tse.name,
    type: tse.type as TseType,
    ws_url: tse.ws_url ?? "",
    ws_timeout: tse.ws_timeout ?? 5,
    password: tse.password ?? "",
    fiskaly_profile: tse.fiskaly_profile,
  };

  return (
    <EditLayout
      title={t("tse.update")}
      successRoute={TseRoutes.detail(tse.id)}
      submitLabel={t("update")}
      initialValues={initialValues}
      validationSchema={UpdateTseSchema}
      onSubmit={(t) => {
        const { type: _type, ...update } = t;
        return updateTse({ nodeId: currentNode.id, tseId: tse.id, updateTse: update });
      }}
      form={UpdateTseForm}
    />
  );
};
