import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import database


class CustomRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = database.load_data()
        self._ensure_db_structure()
        self.auto_check_loop.start()

    def cog_unload(self):
        self.auto_check_loop.cancel()

    def _ensure_db_structure(self):
        """Đảm bảo các key cơ bản luôn tồn tại trong Database."""
        if not isinstance(self.db, dict):
            self.db = {}
        if "links" not in self.db:
            self.db["links"] = {}
        if "booster_roles" not in self.db:
            self.db["booster_roles"] = {}

    # --- ⚠️ TỰ ĐỘNG XỬ LÝ & BÁO LỖI LỆNH ---

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Bắt lỗi khi sử dụng lệnh để phản hồi Embed thay vì im lặng."""
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Thiếu Quyền Hạn",
                description="Bạn cần có quyền **Manage Roles** để thực hiện lệnh này!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="❌ Tham Số Không Hợp Lệ",
                description="Vui lòng kiểm tra lại ID/Mention của Role hoặc User!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Thiếu Tham Số",
                description=f"Vui lòng nhập đầy đủ các tham số cho lệnh `{ctx.command.name}`!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # --- 🔄 VÒNG LẶP KIỂM TRA & ĐỒNG BỘ TỰ ĐỘNG (NGẦM) ---

    @tasks.loop(minutes=1)
    async def auto_check_loop(self):
        """Vòng lặp ngầm chạy 1 phút/lần để quét và đồng bộ Role Custom toàn hệ thống."""
        self.db = database.load_data()
        links_db = self.db.get("links", {})
        booster_db = self.db.get("booster_roles", {})

        if not links_db:
            return

        for guild_id_str, links in links_db.items():
            guild = self.bot.get_guild(int(guild_id_str))
            if not guild:
                continue

            booster_role_id = booster_db.get(guild_id_str)
            if not booster_role_id:
                continue

            booster_role_id = str(booster_role_id)

            for child_id_str, info in links.items():
                owner_user_id = info.get("user_id") if isinstance(info, dict) else str(info)
                if not owner_user_id:
                    continue

                child_role = guild.get_role(int(child_id_str)) if str(child_id_str).isdigit() else None
                if not child_role:
                    continue

                owner_member = guild.get_member(int(owner_user_id)) if str(owner_user_id).isdigit() else None
                if not owner_member and str(owner_user_id).isdigit():
                    try:
                        owner_member = await guild.fetch_member(int(owner_user_id))
                    except discord.NotFound:
                        owner_member = None

                if owner_member:
                    owner_role_ids = {str(r.id) for r in owner_member.roles}

                    if booster_role_id in owner_role_ids and child_id_str not in owner_role_ids:
                        try:
                            await owner_member.add_roles(child_role, reason="Auto-Loop: Phát hiện có Role Booster")
                        except Exception as e:
                            print(f"[AUTO-LOOP ERROR ADD] {e}")

                    elif booster_role_id not in owner_role_ids and child_id_str in owner_role_ids:
                        try:
                            await owner_member.remove_roles(child_role, reason="Auto-Loop: Mất Role Booster")
                        except Exception as e:
                            print(f"[AUTO-LOOP ERROR REMOVE] {e}")

                for member in child_role.members:
                    if str(member.id) != owner_user_id:
                        try:
                            await member.remove_roles(child_role, reason="Auto-Loop: Gỡ role bị cấp sai người")
                        except Exception as e:
                            print(f"[AUTO-LOOP ERROR REVOKE] {e}")

    @auto_check_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_ready()

    # --- 1. LỆNH LIÊN KẾT ROLE CUSTOM ---

    @commands.hybrid_command(name="link", description="Liên kết Role Custom cho một User.")
    @app_commands.describe(child_role="Role Custom cần cấp", member="Thành viên sở hữu role")
    @commands.has_permissions(manage_roles=True)
    async def link_roles(self, ctx, child_role: discord.Role, member: discord.Member):
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)
        booster_role_id = self.db.get("booster_roles", {}).get(guild_id)

        if not booster_role_id:
            embed = discord.Embed(
                title="⚠️ Chưa Thiết Lập Role Booster",
                description="Server chưa thiết lập Role Booster chung!\nVui lòng dùng lệnh `/booster` hoặc `kb.booster` trước.",
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)

        existing_link = self.db.get("links", {}).get(guild_id, {}).get(str(child_role.id))
        if existing_link:
            existing_user_id = existing_link.get("user_id") if isinstance(existing_link, dict) else str(existing_link)
            existing_member = ctx.guild.get_member(int(existing_user_id)) if existing_user_id.isdigit() else None
            existing_owner_text = existing_member.mention if existing_member else f"ID User: `{existing_user_id}`"

            embed = discord.Embed(
                title="❌ Role Đã Được Liên Kết Trước Đó",
                description=(
                    f"Role {child_role.mention} hiện tại đã được gán cho {existing_owner_text}!\n\n"
                    f"💡 *Nếu muốn chuyển role này cho {member.mention}, hãy gõ lệnh hủy liên kết cũ trước:*\n"
                    f"`/unlink {child_role.name}` hoặc `kb.unlink {child_role.mention}`"
                ),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if guild_id not in self.db["links"]:
            self.db["links"][guild_id] = {}

        self.db["links"][guild_id][str(child_role.id)] = {
            "user_id": str(member.id)
        }
        
        try:
            success = await asyncio.to_thread(database.save_data, self.db)
        except Exception as e:
            print(f"[SAVE ERROR] {e}")
            success = False

        if success:
            booster_role = ctx.guild.get_role(int(booster_role_id)) if str(booster_role_id).isdigit() else None
            booster_text = booster_role.mention if booster_role else f"ID `{booster_role_id}`"
            
            user_role_ids = {str(r.id) for r in member.roles}
            
            if booster_role_id in user_role_ids:
                try:
                    await member.add_roles(child_role, reason="Cấp Role Custom khi thực hiện lệnh link")
                    status_text = "✅ **Đã thêm role trực tiếp cho người dùng thành công!**"
                except discord.Forbidden:
                    status_text = "⚠️ *Lưu liên kết thành công nhưng Bot thiếu quyền hoặc vị trí Role của Bot thấp hơn Role Custom.*"
                except Exception as e:
                    status_text = f"❌ *Lưu thành công nhưng gặp lỗi khi add role: {e}*"
            else:
                status_text = "⏳ *Đã lưu liên kết. Người dùng chưa có Role Booster nên sẽ tự động nhận role khi Boost server.*"

            embed = discord.Embed(
                title="✅ Liên Kết Role Custom Thành Công",
                color=discord.Color.green()
            )
            embed.add_field(name="🎭 Role Custom", value=f"{child_role.mention} (ID: `{child_role.id}`)", inline=False)
            embed.add_field(name="👤 Chủ Sở Hữu", value=f"{member.mention} (ID: `{member.id}`)", inline=False)
            embed.add_field(name="⚡ Yêu Cầu", value=f"Có Role Booster ({booster_text})", inline=False)
            embed.add_field(name="📌 Trạng Thái Cấp Role", value=status_text, inline=False)
            
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Lỗi Hệ Thống",
                description="Đã xảy ra lỗi khi lưu vào Database!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # --- 2. LỆNH HỦY LIÊN KẾT & GỠ ROLE ---

    @commands.hybrid_command(name="unlink", description="Hủy liên kết của một Role Custom và gỡ khỏi người dùng.")
    @app_commands.describe(child_role="Role Custom cần hủy liên kết")
    @commands.has_permissions(manage_roles=True)
    async def unlink_roles(self, ctx, child_role: discord.Role):
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)
        if guild_id in self.db["links"] and str(child_role.id) in self.db["links"][guild_id]:
            members_with_role = list(child_role.members)
            removed_count = 0

            for member in members_with_role:
                try:
                    await member.remove_roles(child_role, reason="Hủy liên kết bằng lệnh unlink")
                    removed_count += 1
                except Exception as e:
                    print(f"[UNLINK ERROR REMOVE] {e}")

            del self.db["links"][guild_id][str(child_role.id)]
            
            try:
                await asyncio.to_thread(database.save_data, self.db)
            except Exception as e:
                print(f"[SAVE ERROR] {e}")
            
            description_text = f"Đã gỡ bỏ cài đặt liên kết cho role {child_role.mention}."
            if members_with_role:
                description_text += f"\n🧹 **Đã gỡ role trực tiếp khỏi {removed_count}/{len(members_with_role)} người dùng đang giữ role này.**"
            else:
                description_text += "\nℹ️ *Không có người dùng nào đang giữ role này.*"

            embed = discord.Embed(
                title="✅ Hủy Liên Kết Thành Công",
                description=description_text,
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Lỗi Thực Thi",
                description=f"Role {child_role.mention} chưa từng được thiết lập liên kết nào.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # --- 3. LỆNH KHÔI PHỤC ROLE THỦ CÔNG ---

    @commands.hybrid_command(name="restore", description="Khôi phục thủ công lập tức mà không cần đợi vòng lặp ngầm.")
    @app_commands.describe(member="Thành viên cần khôi phục (để trống nếu muốn quét toàn server)")
    @commands.has_permissions(manage_roles=True)
    async def restore_roles(self, ctx, member: discord.Member = None):
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)
        guild_links = self.db["links"].get(guild_id, {})
        booster_role_id = self.db.get("booster_roles", {}).get(guild_id)

        if not booster_role_id or not guild_links:
            embed = discord.Embed(
                title="⚠️ Chưa Có Dữ Liệu",
                description="Server chưa thiết lập Role Booster hoặc chưa có liên kết nào.",
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)

        target_members = [member] if member else ctx.guild.members
        restored_count = 0

        for target in target_members:
            user_id = str(target.id)
            user_role_ids = {str(r.id) for r in target.roles}
            to_add = []

            if booster_role_id in user_role_ids:
                for child_id_str, info in guild_links.items():
                    owner_user_id = info.get("user_id") if isinstance(info, dict) else str(info)
                    
                    if owner_user_id == user_id and child_id_str not in user_role_ids:
                        role_obj = ctx.guild.get_role(int(child_id_str)) if str(child_id_str).isdigit() else None
                        if role_obj:
                            to_add.append(role_obj)

            if to_add:
                try:
                    await target.add_roles(*to_add, reason="Khôi phục role bằng restore")
                    restored_count += len(to_add)
                except discord.Forbidden:
                    pass

        embed = discord.Embed(
            title="✅ Khôi Phục Thành Công",
            description=f"Đã cấp bổ sung **{restored_count}** role.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # --- 4. LỆNH DỌN DẸP DATABASE SERVER ---

    @commands.hybrid_command(name="clear", description="Xóa toàn bộ dữ liệu cài đặt Role của server này.")
    @commands.has_permissions(administrator=True)
    async def clear_all_data(self, ctx):
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)

        if guild_id in self.db.get("booster_roles", {}):
            del self.db["booster_roles"][guild_id]
            
        if guild_id in self.db.get("links", {}):
            del self.db["links"][guild_id]

        try:
            success = await asyncio.to_thread(database.save_data, self.db)
        except Exception as e:
            print(f"[SAVE ERROR] {e}")
            success = False

        if success:
            embed = discord.Embed(
                title="🧹 Dọn Dẹp Dữ Liệu",
                description="Đã xóa sạch toàn bộ dữ liệu cài đặt role của server này trên Database!",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Lỗi Hệ Thống",
                description="Đã xảy ra lỗi khi cập nhật Database!",
                color=discord.Color.red()
            )
        await ctx.send(embed=embed)

    # --- 5. SỰ KIỆN LẮNG NGHE ĐỔI ROLE REAL-TIME ---

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_role_ids = {str(r.id) for r in before.roles}
        after_role_ids = {str(r.id) for r in after.roles}

        if before_role_ids == after_role_ids:
            return

        guild_id = str(after.guild.id)
        guild_links = self.db.get("links", {}).get(guild_id, {})
        booster_role_id = self.db.get("booster_roles", {}).get(guild_id)

        if not guild_links or not booster_role_id:
            return

        roles_to_remove = []
        roles_to_add = []
        user_id = str(after.id)

        for child_id_str, info in guild_links.items():
            owner_user_id = info.get("user_id") if isinstance(info, dict) else str(info)

            if not owner_user_id:
                continue

            if user_id == owner_user_id:
                if booster_role_id in after_role_ids and child_id_str not in after_role_ids:
                    role_obj = after.guild.get_role(int(child_id_str)) if str(child_id_str).isdigit() else None
                    if role_obj:
                        roles_to_add.append(role_obj)
                
                elif booster_role_id not in after_role_ids and child_id_str in after_role_ids:
                    role_obj = after.guild.get_role(int(child_id_str)) if str(child_id_str).isdigit() else None
                    if role_obj:
                        roles_to_remove.append(role_obj)
            else:
                if child_id_str in after_role_ids:
                    role_obj = after.guild.get_role(int(child_id_str)) if str(child_id_str).isdigit() else None
                    if role_obj:
                        roles_to_remove.append(role_obj)

        if roles_to_add:
            try:
                await after.add_roles(*roles_to_add, reason="Liên kết ngầm: Có Role Booster")
            except Exception as e:
                print(f"[LỖI ADD] {e}")

        if roles_to_remove:
            try:
                await after.remove_roles(*roles_to_remove, reason="Liên kết ngầm: Mất Role Booster hoặc sai chủ sở hữu")
            except Exception as e:
                print(f"[LỖI REMOVE] {e}")


async def setup(bot):
    await bot.add_cog(CustomRole(bot))
    
