"use client"

import { SettingsForm } from "@/components/forms/SettingsForm"

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-foreground">Settings</h1>
      <SettingsForm />
    </div>
  )
}
