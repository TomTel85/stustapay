export type {
  FiskalyProvisioningJob,
  FiskalySite,
  NewFiskalyProvisioningJob,
  NewFiskalySite,
} from "./generated/api";

export type CreateFiskalySite = import("./generated/api").NewFiskalySite;
export type FiskalyEnvironment = NonNullable<import("./generated/api").NewFiskalyProvisioningJob["environment"]>;
export type FiskalyProvisioningStatus = import("./generated/api").FiskalyProvisioningJob["status"];

export {
  useListSitesQuery as useListFiskalySitesQuery,
  useCreateSiteMutation as useCreateFiskalySiteMutation,
  useSiteStatusQuery as useGetFiskalySiteStatusQuery,
  useStartProvisioningMutation as useStartFiskalyProvisioningMutation,
  useSetFiskalyProvisioningPausedMutation,
  useRetryProvisioningMutation as useRetryFiskalyProvisioningMutation,
} from "./api";
