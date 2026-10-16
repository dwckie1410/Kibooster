import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import database


# ==============================================================================
# CLASS TẠO GIAO DIỆN NÚT BẤM CHUYỂN TRANG CHO LỆNH LIST (10 ITEMS / TRANG)
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
# COG QUẢN LÝ CẤU HÌNH & XEM DANH SÁCH ROLE
# ==============================================================================

class RoleViewsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = database.load_data()
        self._ensure_db_structure()

    def _ensure_db_structure(self):
        """Đảm bảo các key cơ bản luôn tồn tại trong Database."""
        if not isinstance(self.db, dict):
            self.db = {}
        if "links" not in self.db:
            self.db["links"] = {}
        if "booster_roles" not in self.db:
            self.db["booster_roles"] = {}

    # --- 1. LỆNH CẤU HÌNH ROLE BOOSTER DÙNG CHUNG ---

    @commands.hybrid_command(name="booster", description="Thiết lập Role Booster cố định cho server.")
    @app_commands.describe(booster_role="Role Booster chung của Server")
    @commands.has_permissions(manage_roles=True)
    async def set_booster_role(self, ctx, booster_role: discord.Role):
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
                    f"📌 *Có thể dùng Slash:* `/link <role_custom> <user>` hoặc `kb.link <@role> <@user>`"
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

    # --- 2. LỆNH XEM DANH SÁCH (PHÂN TRANG 10 ITEMS + BUTTONS) ---

    @commands.hybrid_command(name="list", description="Xem danh sách Role Booster chung và các Role Custom.")
    async def list_links(self, ctx):
        try:
            self.db = database.load_data()  # Cập nhật dữ liệu mới nhất
            self._ensure_db_structure()
            guild_id = str(ctx.guild.id)
            links = self.db.get("links", {}).get(guild_id, {})
            booster_role_id = self.db.get("booster_roles", {}).get(guild_id)

            booster_role = None
            if booster_role_id and str(booster_role_id).isdigit():
                booster_role = ctx.guild.get_role(int(booster_role_id))

            booster_name = (
                booster_role.mention if booster_role 
                else (f"ID: `{booster_role_id}`" if booster_role_id 
                else "❌ *Chưa thiết lập*")
            )

            if not links:
                embed = discord.Embed(title="🔗 Danh Sách Role Custom", color=discord.Color.blue())
                embed.description = f"⚡ **Role Booster chung:** {booster_name}\n"
                embed.add_field(name="Thông báo", value="Chưa có liên kết role custom nào.", inline=False)
                return await ctx.send(embed=embed)

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
            await ctx.send(error_embed)


async def setup(bot):
    await bot.add_cog(RoleViewsCog(bot))
