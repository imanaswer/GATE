import { redirect } from "next/navigation";
import { LandingDesktop } from "@/components/LandingDesktop";
import { createClient } from "@/lib/supabase/server";

export default async function Landing({ searchParams }: PageProps<"/">) {
  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : "/register";

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user) redirect(next.startsWith("/") ? next : "/register");

  return <LandingDesktop next={next} />;
}
