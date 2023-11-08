import { Tse, selectTseAll, useListTsesQuery } from "@/api";
import { useCurrentNode } from "@/hooks";
import { Select, SelectProps } from "@stustapay/components";
import * as React from "react";

export type TillTseSelectProps = Omit<
  SelectProps<Tse, number, false>,
  "options" | "formatOption" | "multiple" | "getOptionKey"
>;

export const TillTseSelect: React.FC<TillTseSelectProps> = (props) => {
  const { currentNode } = useCurrentNode();
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
    <Select
      multiple={false}
      options={tses}
      getOptionKey={(tse: Tse) => tse.id}
      formatOption={(tse: Tse) => tse.name}
      {...props}
    />
  );
};
