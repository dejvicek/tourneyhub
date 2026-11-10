import { queryOptions } from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";

export const authQueries = {
  me: () =>
    queryOptions({
      queryKey: ["me"],
      queryFn: ({ signal }) => dataOf(api.GET("/api/v1/me", { signal })),
    }),
};
