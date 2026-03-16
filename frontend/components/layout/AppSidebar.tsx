"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"
import { useAuth } from "@/lib/auth"
import { UserMenu } from "./UserMenu"
import { CalendarDays, Users, QrCode, Shield, Settings } from "lucide-react"

const NAV_ITEMS = [
  { href: "/visits", label: "Visits", icon: CalendarDays, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/visitors", label: "Visitors", icon: Users, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/invitations", label: "Invitations", icon: QrCode, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/users", label: "Users", icon: Shield, roles: ["PROPERTY_ADMIN", "SUPER_ADMIN"] },
  { href: "/settings", label: "Settings", icon: Settings, roles: ["TENANT_USER", "PROPERTY_ADMIN", "SUPER_ADMIN"] },
]

export function AppSidebar() {
  const pathname = usePathname()
  const { user } = useAuth()

  const visibleItems = NAV_ITEMS.filter(
    (item) => !user?.role || item.roles.includes(user.role),
  )

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="border-b border-sidebar-border px-4 py-3">
        <span className="text-sm font-bold text-primary group-data-[collapsible=icon]:hidden">
          Habitare
        </span>
        <span className="hidden text-sm font-bold text-primary group-data-[collapsible=icon]:block">H</span>
      </SidebarHeader>

      <SidebarContent>
        <SidebarMenu className="px-2 py-2">
          {visibleItems.map((item) => {
            const isActive = pathname.startsWith(item.href)
            return (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton
                  asChild
                  isActive={isActive}
                  tooltip={item.label}
                  className={isActive ? "bg-primary/20 text-primary hover:bg-primary/30" : ""}
                >
                  <Link href={item.href}>
                    <item.icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border p-2">
        <SidebarMenu>
          <SidebarMenuItem>
            <UserMenu />
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
