"use client"

import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useState } from "react"
import { format, addDays } from "date-fns"
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
import { Calendar } from "@/components/ui/calendar"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { CalendarIcon } from "lucide-react"
import { apiFetch, ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

const schema = z.object({
  visitor_email: z.string().email("Enter a valid email"),
  visitor_name: z.string().min(1, "Visitor name is required"),
  unit_number: z.string().optional(),
})

type FormData = z.infer<typeof schema>

interface CreateInvitationFormProps {
  open: boolean
  onClose: () => void
}

export function CreateInvitationForm({ open, onClose }: CreateInvitationFormProps) {
  const queryClient = useQueryClient()
  const [expiresAt, setExpiresAt] = useState<Date>(addDays(new Date(), 7))
  const [calOpen, setCalOpen] = useState(false)

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  async function onSubmit(data: FormData) {
    try {
      await apiFetch("/invitations/", {
        method: "POST",
        body: JSON.stringify({
          ...data,
          unit_number: data.unit_number || null,
          expires_at: expiresAt.toISOString(),
        }),
      })
      toast.success("Invitation created")
      queryClient.invalidateQueries({ queryKey: ["invitations"] })
      reset()
      setExpiresAt(addDays(new Date(), 7))
      onClose()
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && Array.isArray(err.detail)) {
        // Map FastAPI validation errors to inline field errors
        for (const item of err.detail as Array<{ loc: string[]; msg: string }>) {
          const field = item.loc[item.loc.length - 1] as keyof FormData
          setError(field, { message: item.msg })
        }
      } else {
        toast.error(err instanceof ApiError ? err.message : "Failed to create invitation")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="bg-card border-border">
        <DialogHeader>
          <DialogTitle>Create Invitation</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4 pt-2">
          <div className="flex flex-col gap-1.5">
            <Label>Visitor Email *</Label>
            <Input placeholder="visitor@example.com" {...register("visitor_email")} />
            {errors.visitor_email && <p className="text-xs text-destructive">{errors.visitor_email.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Visitor Name *</Label>
            <Input placeholder="Jane Doe" {...register("visitor_name")} />
            {errors.visitor_name && <p className="text-xs text-destructive">{errors.visitor_name.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Unit Number</Label>
            <Input placeholder="4B (optional)" {...register("unit_number")} />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Expires At *</Label>
            <Popover open={calOpen} onOpenChange={setCalOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className={cn("justify-start text-left font-normal")}>
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {format(expiresAt, "PPP")}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0">
                <Calendar
                  mode="single"
                  selected={expiresAt}
                  onSelect={(d) => { if (d) { setExpiresAt(d); setCalOpen(false) } }}
                  disabled={(d) => d < new Date()}
                />
              </PopoverContent>
            </Popover>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating\u2026" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
