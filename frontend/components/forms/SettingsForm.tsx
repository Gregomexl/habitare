"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useEffect } from "react"
import { toast } from "sonner"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiFetch, ApiError } from "@/lib/api"
import { useAuth } from "@/lib/auth"

interface UserProfile {
  id: string
  email: string
  full_name: string | null
  phone_number: string | null
  unit_number: string | null
  role: string
}

const schema = z.object({
  full_name: z.string().optional(),
  phone_number: z.string().optional(),
  unit_number: z.string().optional(),
})

type FormData = z.infer<typeof schema>

export function SettingsForm() {
  const { updateUser } = useAuth()

  const { data: profile, isLoading } = useQuery<UserProfile>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<UserProfile>("/users/me"),
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting, isDirty },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  // Populate form once profile loads
  useEffect(() => {
    if (profile) {
      reset({
        full_name: profile.full_name ?? "",
        phone_number: profile.phone_number ?? "",
        unit_number: profile.unit_number ?? "",
      })
    }
  }, [profile, reset])

  async function onSubmit(data: FormData) {
    try {
      const updated = await apiFetch<UserProfile>("/users/me", {
        method: "PUT",
        body: JSON.stringify({
          full_name: data.full_name || null,
          phone_number: data.phone_number || null,
          unit_number: data.unit_number || null,
        }),
      })
      // User interface uses camelCase; API response uses snake_case — map explicitly
      updateUser({
        email: updated.email,
        fullName: updated.full_name ?? undefined,
        phoneNumber: updated.phone_number ?? undefined,
        unitNumber: updated.unit_number ?? undefined,
      })
      toast.success("Profile updated")
      reset({
        full_name: updated.full_name ?? "",
        phone_number: updated.phone_number ?? "",
        unit_number: updated.unit_number ?? "",
      })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to update profile")
    }
  }

  if (isLoading) {
    return <div className="text-muted-foreground">Loading\u2026</div>
  }

  return (
    <Card className="max-w-lg">
      <CardHeader>
        <CardTitle>Profile</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Email</span>
          <span className="text-sm text-foreground">{profile?.email}</span>
        </div>
        <div className="mb-6 flex flex-col gap-1">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Role</span>
          <span className="text-sm text-foreground capitalize">
            {profile?.role?.toLowerCase().replace("_", " ")}
          </span>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Full Name</Label>
            <Input placeholder="Your name" {...register("full_name")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Phone Number</Label>
            <Input placeholder="+1 555 0100" {...register("phone_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Unit Number</Label>
            <Input placeholder="4B" {...register("unit_number")} />
          </div>

          <Button type="submit" className="self-start" disabled={isSubmitting || !isDirty}>
            {isSubmitting ? "Saving\u2026" : "Save changes"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
