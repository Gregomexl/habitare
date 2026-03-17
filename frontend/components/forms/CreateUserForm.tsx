"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useState } from "react"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { apiFetch, ApiError } from "@/lib/api"

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  full_name: z.string().optional(),
  phone_number: z.string().optional(),
  unit_number: z.string().optional(),
  role: z.enum(["TENANT_USER", "PROPERTY_ADMIN"]),
})

type FormData = z.infer<typeof schema>

interface CreateUserResponse {
  id: string
  email: string
  temp_password: string
}

interface CreateUserFormProps {
  open: boolean
  onClose: () => void
}

export function CreateUserForm({ open, onClose }: CreateUserFormProps) {
  const queryClient = useQueryClient()
  const [tempPassword, setTempPassword] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { role: "TENANT_USER" },
  })

  async function onSubmit(data: FormData) {
    try {
      const resp = await apiFetch<CreateUserResponse>("/users/", {
        method: "POST",
        body: JSON.stringify({
          email: data.email,
          full_name: data.full_name || null,
          phone_number: data.phone_number || null,
          unit_number: data.unit_number || null,
          role: data.role,
        }),
      })
      setTempPassword(resp.temp_password)
      queryClient.invalidateQueries({ queryKey: ["users"] })
      reset()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && Array.isArray(err.detail)) {
        // Map FastAPI validation errors to inline field errors
        for (const item of err.detail as Array<{ loc: string[]; msg: string }>) {
          const field = item.loc[item.loc.length - 1] as keyof FormData
          setError(field, { message: item.msg })
        }
      } else {
        toast.error(err instanceof ApiError ? err.message : "Failed to create user")
      }
    }
  }

  function handleClose() {
    setTempPassword(null)
    onClose()
  }

  // Show temp password dialog after creation
  if (tempPassword) {
    return (
      <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose() }}>
        <DialogContent className="bg-card border-border">
          <DialogHeader>
            <DialogTitle>User Created</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3 py-2">
            <p className="text-sm text-muted-foreground">
              Share this temporary password with the new user. It will not be shown again.
            </p>
            <div className="rounded-md border border-border bg-background p-3 font-mono text-primary text-lg tracking-widest text-center">
              {tempPassword}
            </div>
          </div>
          <DialogFooter>
            <Button onClick={handleClose}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose() }}>
      <DialogContent className="bg-card border-border">
        <DialogHeader>
          <DialogTitle>Add User</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 pt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Email *</Label>
            <Input placeholder="staff@example.com" {...register("email")} />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Full Name</Label>
            <Input placeholder="Jane Doe" {...register("full_name")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Phone Number</Label>
            <Input placeholder="+1 555 0100" {...register("phone_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Unit Number</Label>
            <Input placeholder="4B" {...register("unit_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Role *</Label>
            <Select onValueChange={(v) => setValue("role", v as "TENANT_USER" | "PROPERTY_ADMIN")} defaultValue="TENANT_USER">
              <SelectTrigger>
                <SelectValue placeholder="Select role" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="TENANT_USER">Tenant User</SelectItem>
                <SelectItem value="PROPERTY_ADMIN">Property Admin</SelectItem>
              </SelectContent>
            </Select>
            {errors.role && <p className="text-xs text-destructive">{errors.role.message}</p>}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating\u2026" : "Add User"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
