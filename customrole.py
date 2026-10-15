import asyncio
import discord
from discord.ext import commands, tasks
import database


# ==============================================================================
# CLASS TẠO GIAO DIỆN NÚT BẤM CHUYỂN TRANG CHO KB.LIST (10 ITEMS / TRANG)
# ==============================================================================

class RoleListView(discord.ui.View):
    def __init__(self, ctx, pages):
        super().__init__(timeout=120)  # Nút bấm hoạt động trong 120 giây
        self.ctx = ctx
        self.pages = pages
        self.current_page = 0
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        """Cập nhật trạng thái bật/tắt của các nút theo trang hiện tại."""
        self.btn_prev.disabled = (self.current_page == 0)
        self.btn_next.disabled = (self.current_page == len(self.pages) - 1)
        self.btn_page.label = f"Trang {self.current_page + 1}/{len(self.pages)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Đảm bảo chỉ người dùng gõ lệnh mới có thể bấm nút."""
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "❌ Bạn không thể dùng nút chuyển trang của người khác!", 
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary, custom_id="prev_btn")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Trang 1/1", style=discord.ButtonStyle.secondary, disabled=True, custom_id="page_indicator")
    async def btn_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary, custom_id="next_btn")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def on_timeout(self):
        """Vô hiệu hóa nút bấm khi hết thời gian chờ."""
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ==============================================================================
# MAIN COG: CUSTOM ROLE MANAGEMENT
# ==============================================================================

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

    # --- ⚠️ TỰ ĐỘNG XỬ LÝ & BÁO LỖI LỆNH PREFIX ---

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Bắt lỗi khi sử dụng prefix kb. để phản hồi Embed thay vì im lặng."""
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
                description="Vui lòng kiểm tra lại ID/Mention của Role hoặc User (Đảm bảo tag đúng hoặc dán đúng ID)!",
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

                # 1. Kiểm tra và cấp/gỡ role cho đúng chủ sở hữu
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

                # 2. Gỡ role nếu bị trao nhầm cho thành viên khác
                for member in child_role.members:
                    if str(member.id) != owner_user_id:
                        try:
                            await member.remove_roles(child_role, reason="Auto-Loop: Gỡ role bị cấp sai người")
                        except Exception as e:
                            print(f"[AUTO-LOOP ERROR REVOKE] {e}")

    @auto_check_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_ready()

    # --- 1. LỆNH CẤU HÌNH ROLE BOOSTER DÙNG CHUNG ---

    @commands.command(name="booster")
    @commands.has_permissions(manage_roles=True)
    async def set_booster_role(self, ctx, booster_role: discord.Role):
        """Thiết lập Role Booster cố định cho server."""
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)
        self.db["booster_roles"][guild_id] = str(booster_role.id)
        
        try:
            success = await asyncio.to_thread(database.save_data, self.db)
        except Exception as e:
            print(f"[SAVE ERROR] {e}")
            success = False

        if success:
            embed = discord.Embed(
                title="✅ Cài Đặt Role Booster Thành Công",
                description=(
                    f"⚡ **Role Booster chung:** {booster_role.mention} (ID: `{booster_role.id}`)\n\n"
                    f"📌 *Cú pháp liên kết:* `kb.link <@role_custom> <@user>`"
                ),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Lỗi Hệ Thống",
                description="Đã xảy ra lỗi khi lưu dữ liệu vào Database!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # --- 2. LỆNH LIÊN KẾT ROLE CUSTOM ---

    @commands.command(name="link")
    @commands.has_permissions(manage_roles=True)
    async def link_roles(self, ctx, child_role: discord.Role, member: discord.Member):
        """Liên kết Role Custom cho một User và tự động cấp role nếu có Booster."""
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)
        booster_role_id = self.db.get("booster_roles", {}).get(guild_id)

        # 1. Kiểm tra xem Server đã cấu hình Role Booster chung chưa
        if not booster_role_id:
            embed = discord.Embed(
                title="⚠️ Chưa Thiết Lập Role Booster",
                description="Server chưa thiết lập Role Booster chung!\nVui lòng dùng lệnh `kb.booster <@role_booster>` trước.",
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)

        # 2. Kiểm tra trùng lặp: Nếu role này đã link cho người khác
        existing_link = self.db.get("links", {}).get(guild_id, {}).get(str(child_role.id))
        if existing_link:
            existing_user_id = existing_link.get("user_id") if isinstance(existing_link, dict) else str(existing_link)
            existing_member = ctx.guild.get_member(int(existing_user_id)) if existing_user_id.isdigit() else None
            existing_owner_text = existing_member.mention if existing_member else f"ID User: `{existing_user_id}`"

            embed = discord.Embed(
                title="❌ Role Đã Được Liên Kết Trước Đó",
                description=(
                    f"Role {child_role.mention} hiện tại đã được gán cho {existing_owner_text}!\n\n"
                    f"💡 *Nếu muốn chuyển role này cho {member.mention}, bạn cần gõ lệnh bên dưới để hủy liên kết cũ trước:*\n"
                    f"`kb.unlink {child_role.mention}`"
                ),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # 3. Tạo dữ liệu liên kết mới
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
            
            # Cấp role trực tiếp nếu người đó đang có Role Booster
            if booster_role_id in user_role_ids:
                try:
                    await member.add_roles(child_role, reason="Cấp Role Custom khi thực hiện lệnh kb.link")
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

    # --- 3. LỆNH HỦY LIÊN KẾT & GỠ ROLE ---

    @commands.command(name="unlink")
    @commands.has_permissions(manage_roles=True)
    async def unlink_roles(self, ctx, child_role: discord.Role):
        """Hủy liên kết của một Role Custom và tự động gỡ role khỏi thành viên."""
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)
        if guild_id in self.db["links"] and str(child_role.id) in self.db["links"][guild_id]:
            # Gỡ role trực tiếp từ tất cả các member đang giữ role này
            members_with_role = list(child_role.members)
            removed_count = 0

            for member in members_with_role:
                try:
                    await member.remove_roles(child_role, reason="Hủy liên kết bằng lệnh kb.unlink")
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

    # --- 4. LỆNH XEM DANH SÁCH (PHÂN TRANG 10 ITEMS + BUTTONS) ---

    @commands.command(name="list")
    async def list_links(self, ctx):
        """Xem danh sách Role Booster chung và các Role Custom trong server (10 role/trang)."""
        try:
            self._ensure_db_structure()
            guild_id = str(ctx.guild.id)
            links = self.db.get("links", {}).get(guild_id, {})
            booster_role_id = self.db.get("booster_roles", {}).get(guild_id)

            # Lấy thông tin Role Booster chung
            booster_role = None
            if booster_role_id and str(booster_role_id).isdigit():
                booster_role = ctx.guild.get_role(int(booster_role_id))

            booster_name = (
                booster_role.mention if booster_role 
                else (f"ID: `{booster_role_id}`" if booster_role_id 
                else "❌ *Chưa thiết lập (Dùng kb.booster)*")
            )

            if not links:
                embed = discord.Embed(title="🔗 Danh Sách Role Custom", color=discord.Color.blue())
                embed.description = f"⚡ **Role Booster chung:** {booster_name}\n"
                embed.add_field(name="Thông báo", value="Chưa có liên kết role custom nào.", inline=False)
                return await ctx.send(embed=embed)

            # Chia danh sách role thành các nhóm 10 item/trang
            items = list(links.items())
            chunk_size = 10
            chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

            pages = []
            total_pages = len(chunks)

            for page_index, chunk in enumerate(chunks, start=1):
                embed = discord.Embed(title="🔗 Danh Sách Role Custom", color=discord.Color.blue())
                embed.description = (
                    f"⚡ **Role Booster chung:** {booster_name}\n"
                    f"🔄 **Chế độ quét:** Tự động check ngầm mỗi 1 phút\n"
                    f"📊 **Tổng số role liên kết:** `{len(items)}`"
                )

                for child_id_str, info in chunk:
                    if isinstance(info, dict):
                        user_id = info.get("user_id")
                    else:
                        user_id = str(info)

                    child_role = ctx.guild.get_role(int(child_id_str)) if str(child_id_str).isdigit() else None
                    owner_member = ctx.guild.get_member(int(user_id)) if user_id and str(user_id).isdigit() else None

                    title_text = child_role.name if child_role else f"Role ID: {child_id_str}"
                    child_mention = child_role.mention if child_role else f"`{child_id_str}`"
                    owner_mention = owner_member.mention if owner_member else (f"`{user_id}`" if user_id else "Không xác định")

                    embed.add_field(
                        name=f"📌 {title_text}", 
                        value=f"🎭 **Role Custom:** {child_mention}\n👤 **Chủ sở hữu:** {owner_mention}", 
                        inline=False
                    )

                embed.set_footer(text=f"Trang {page_index}/{total_pages} • Sử dụng nút bấm bên dưới để chuyển trang")
                pages.append(embed)

            # Phân nhánh hiển thị theo số lượng trang
            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            else:
                view = RoleListView(ctx, pages)
                view.message = await ctx.send(embed=pages[0], view=view)

        except Exception as e:
            print(f"[LIST ERROR] {e}")
            error_embed = discord.Embed(
                title="❌ Lỗi Hiển Thị Danh Sách",
                description=f"Đã xảy ra lỗi: `{e}`",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed)

    # --- 5. LỆNH KHÔI PHỤC ROLE THỦ CÔNG ---

    @commands.command(name="restore")
    @commands.has_permissions(manage_roles=True)
    async def restore_roles(self, ctx, member: discord.Member = None):
        """Khôi phục thủ công lập tức mà không cần đợi vòng lặp ngầm."""
        self._ensure_db_structure()
        guild_id = str(ctx.guild.id)
        guild_links = self.db.get("links", {}).get(guild_id, {})
        booster_role_id = self.db.get("booster_roles", {}).get(guild_id)

        if not booster_role_id or not guild_links:
            embed = discord.Embed(
                title="⚠️ Chưa Có Dữ Liệu",
                description="Server chưa thiết lập Role Booster (`kb.booster`) hoặc chưa có liên kết nào.",
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
                    await target.add_roles(*to_add, reason="Khôi phục role bằng kb.restore")
                    restored_count += len(to_add)
                except discord.Forbidden:
                    pass

        embed = discord.Embed(
            title="✅ Khôi Phục Thành Công",
            description=f"Đã cấp bổ sung **{restored_count}** role.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # --- 6. LỆNH DỌN DẸP / RESET DATABASE SERVER ---

    @commands.command(name="clear")
    @commands.has_permissions(administrator=True)
    async def clear_all_data(self, ctx):
        """Xóa toàn bộ dữ liệu cài đặt Role của server này."""
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

    # --- 7. SỰ KIỆN LẮNG NGHE ĐỔI ROLE REAL-TIME ---

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
