from loguru import logger
from typing import Optional, List, Any, Literal
from dataclasses import dataclass, replace

from . import ArrService, ArrVariant, Action, ServiceContent, find_first, is_int
from .ext import ExtArrService
from ..tg_handler import command, callback, handler
from ..tg_handler.message import (
    Response,
    repaint,
    clear,
)
from ..tg_handler.auth import authorized, AuthLevels, get_auth_level_from_message
from ..tg_handler.session_state import (
    sessionState,
    default_session_state_key_fn,
)
from ..tg_handler.keyboard import Button, keyboard


@dataclass(frozen=True)
class State:
    items: List[Any]
    index: int
    quality_profile: str
    language_profile: str
    tags: List[str]
    root_folder: str
    menu: Optional[
        Literal["path"]
        | Literal["tags"]
        | Literal["quality"]
        | Literal["language"]
        | Literal["add"]
    ]


@handler
class Sonarr(ExtArrService, ArrService):
    def __init__(
        self,
        commands: List[str],
        api_host: str,
        api_key: str,
        name: str = None,
        addons: List[ArrService] = []
    ):
        self.commands = commands
        self.api_key = api_key

        self.api_version = self.detect_api(api_host)
        self.service_content = ServiceContent.SERIES
        self.arr_variant = ArrVariant.SONARR
        self.root_folders = self.get_root_folders()
        self.quality_profiles = self.get_quality_profiles()
        self.language_profiles = self.get_language_profiles()

        self.name = name
        self.supported_addons = [ArrVariant.BAZARR]
        self.addons = addons

    @keyboard
    def keyboard(self, state: State, allow_edit=None):
        item = state.items[state.index]
        in_library = "id" in item and item["id"]

        rows_menu = []
        if state.menu == "add":
            if in_library:
                row_navigation = [Button("=== Editing Series ===", "noop")]
            else:
                row_navigation = [Button("=== Adding Series ===", "noop")]
            rows_menu = [
                [
                    Button(
                        f"Change Quality   ({state.quality_profile.get('name', '-')})",
                        self.get_clbk("quality", state.index),
                    ),
                ],
                [
                    Button(
                        f"Change Path   ({state.root_folder.get('path', '-')})",
                        self.get_clbk("path", state.index),
                    )
                ],
                [
                    Button(
                        f"Change Language   ({state.language_profile.get('name', '-')})",
                        self.get_clbk("language", state.index),
                    )
                ],
                # TODO: add more option, not dependent on bazarr integration
                [
                    Button(
                        f"View Seasons",
                        self.get_clbk("seasons", state.index),
                    )
                ],

                #      [
                #          Button(
                #              f"Change Tags   (Total: {len(state.tags)})",
                #              self.get_clbk("tags", state.index),
                #          ),
                #      ],
            ]

        elif state.menu == "tags":
            row_navigation = [Button("=== Selecting Tags ===")]
            tags = self.get_tags() or []
            rows_menu = [
                (
                    [
                        Button(
                            (
                                f"Tag {tag.get('label', '-')}"
                                if tag not in state.tags
                                else f"Remove {tag.get('label', '-')}"
                            ),
                            self.get_clbk("addtag", tag.get("id")),
                        )
                    ]
                    for tag in tags
                ),
                [
                    Button(
                        "Done",
                        self.get_clbk("addmenu"),
                    )
                ],
            ]
        elif state.menu == "path":
            row_navigation = [Button("=== Selecting Root Folder ===")]
            rows_menu = [
                [
                    Button(
                        p.get("path", "-"),
                        self.get_clbk("selectpath", p.get("id")),
                    )
                ]
                for p in self.root_folders
            ]
        elif state.menu == "quality":
            row_navigation = [Button("=== Selecting Quality Profile ===")]
            rows_menu = [
                [
                    Button(
                        p.get("name", "-"),
                        self.get_clbk("selectquality", p.get("id")),
                    )
                ]
                for p in self.quality_profiles
            ]
        elif state.menu == "language":
            row_navigation = [Button("=== Selecting Language Profile ===")]
            rows_menu = [
                [
                    Button(
                        p.get("name", "-"),
                        self.get_clbk("selectlanguage", p.get("id")),
                    )
                ]
                for p in self.language_profiles
            ]
        
        elif state.menu == "seasons":
            row_navigation = []
            rows_menu = self.get_btn_seasons(item["id"])

        elif state.menu == "episodes":
            row_navigation = []
            rows_menu = self.get_btn_episodes(item["id"], item["selectedSeasonNumber"])

        elif state.menu == "episode":
            row_navigation = []

        else:
            if in_library:
                monitored = item.get("monitored", True)
                missing = not item.get("hasFile", False)
                rows_menu = [
                    [
                        Button("📺 Monitored" if monitored else "Unmonitored"),
                        Button("💾 Missing" if missing else "Downloaded"),
                    ]
                ]
            row_navigation = [
                (
                    Button("⬅ Prev", self.get_clbk("goto", state.index - 1))
                    if state.index > 0
                    else Button()
                ),
                (
                    # TODO pjordan: Find replacement
                    Button(
                        "TMDB",
                        url=f"https://www.themoviedb.org/movie/{item['tmdbId']}",
                    )
                    if item.get("tmdbId", None)
                    else None
                ),
                (
                    Button("IMDB", url=f"https://imdb.com/title/{item['imdbId']}")
                    if item.get("imdbId", None)
                    else None
                ),
                (
                    Button("Next ➡", self.get_clbk("goto", state.index + 1))
                    if state.index < len(state.items) - 1
                    else Button()
                ),
            ]
        
        for addon in self.addons:
            addon_buttons = addon.addon_buttons(parent=self, state=state)
            rows_menu.append(addon_buttons)

        rows_action = []
        if in_library:
            if allow_edit:
                if state.menu != "add":
                    rows_action.append(
                        [
                            Button(f"🗑 Remove", self.get_clbk("remove")),
                            Button(f"✏️ Edit", self.get_clbk("addmenu")),
                        ]
                    )
                else:
                    rows_action.append(
                        [
                            Button(f"🗑 Remove", self.get_clbk("remove")),
                            Button(f"✅ Submit", self.get_clbk("add", "no-search")),
                        ]
                    )
                    rows_action.append(
                        [
                            Button(f"✅ + 🔍 Submit & Search", self.get_clbk("add", "search")),
                        ]
                    )
        else:
            if not state.menu:
                rows_action.append([Button(f"➕ Add", self.get_clbk("addmenu"))])
            elif state.menu == "add":
                rows_action.append(
                    [
                        Button(f"✅ Submit", self.get_clbk("add", "no-search")),
                        Button(
                            f"✅+🔍 Submit & Search", self.get_clbk("add", "search")
                        ),
                    ]
                )

        if state.menu == "episodes":
            rows_action.append([Button("🔙 Back", self.get_clbk("goto", "seasons"))])
        elif state.menu == "episode":
            rows_action.append([Button("🔙 Back", self.get_clbk("goto", "episodes"))])
        elif state.menu:
            rows_action.append([Button("🔙 Back", self.get_clbk("goto"))])
        else:
            rows_action.append([Button("❌ Cancel", self.get_clbk("cancel"))])

        return [row_navigation, *rows_menu, *rows_action]

    def create_message(self, state: State, full_redraw=False, allow_edit=False):
        if not state.items:
            return Response(
                caption="No series found",
                state=state,
            )

        item = state.items[state.index]

        keyboard_markup = self.keyboard(state, allow_edit=allow_edit)

        reply_message = self.media_caption(item)

        return Response(
            photo=item.get("remotePoster") if full_redraw else None,
            caption=reply_message,
            reply_markup=keyboard_markup,
            state=state,
        )

    @repaint
    @command(
        default=True,
        default_pattern="<title>",
        default_description="Search for a series",
        cmds=[("search", "<title>", "Search for a series")],
    )
    @sessionState(init=True)
    @authorized(min_auth_level=AuthLevels.USER.value)
    async def cmd_default(self, update, context, args):
        if len(args) > 1 and args[0] == "search":
            args = args[1:]
        title = " ".join(args)

        items = self.lookup(title)
        state = State(
            items=items,
            index=0,
            root_folder=(
                find_first(
                    self.root_folders,
                    lambda x: items[0].get("folderName").startswith(x.get("path")),
                )
                if items
                else None
            ),
            quality_profile=(
                find_first(
                    self.quality_profiles,
                    lambda x: items[0].get("qualityProfileId") == x.get("id"),
                )
                if items
                else None
            ),
            language_profile=(
                find_first(
                    self.language_profiles,
                    lambda x: items[0].get("languageProfileId") == x.get("id"),
                )
                if items
                else None
            ),
            tags=items[0].get("tags", []) if items else None,
            menu=None,
        )

        self.session_db.add_session_entry(
            default_session_state_key_fn(self, update), state
        )

        auth_level = get_auth_level_from_message(self.db, update)
        allow_edit = auth_level >= AuthLevels.MOD.value
        return self.create_message(state, full_redraw=True, allow_edit=allow_edit)

    @command(cmds=[("help", "", "Shows only the sonarr help page")])
    async def cmd_help(self, update, context, args):
        return await ExtArrService.cmd_help(self, update, context, args)

    @repaint
    @command(cmds=[("queue", "", "Shows the sonarr download queue")])
    @authorized(min_auth_level=AuthLevels.USER.value)
    async def cmd_queue(self, update, context, args):
        return await ExtArrService.cmd_queue(self, update, context, args)

    @repaint
    @callback(cmds=["queue"])
    @authorized(min_auth_level=AuthLevels.USER.value)
    async def clbk_queue(self, update, context, args):
        return await ExtArrService.clbk_queue(self, update, context, args)

    @repaint
    @callback(
        cmds=[
            "goto",
            "tags",
            "addtag",
            "remtag",
            "path",
            "selectpath",
            "quality",
            "selectquality",
            "language",
            "selectlanguage",
            "addmenu",
        ]
    )
    @sessionState()
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_update(self, update, context, args, state):
        auth_level = get_auth_level_from_message(self.db, update)
        allow_edit = auth_level >= AuthLevels.MOD.value
        # Prevent any changes from being made if in library and permission level below MOD
        if args[0] in [
            "addtag",
            "remtag",
            "selectpath",
            "selectquality",
            "selectlanguage",
        ]:
            item = state.items[state.index]
            if "id" in item and item["id"] and not allow_edit:
                # Don't do anything, illegal operation
                return self.create_message(state, allow_edit=False)

        full_redraw = False
        if args[0] == "goto":
            if len(args) > 1 and is_int(args[1]):
                idx = int(args[1])
                item = state.items[idx]
                state = replace(
                    state,
                    index=idx,
                    root_folder=find_first(
                        self.root_folders,
                        lambda x: item.get("folderName").startswith(x.get("path")),
                    ),
                    quality_profile=find_first(
                        self.quality_profiles,
                        lambda x: item.get("qualityProfileId") == x.get("id"),
                    ),
                    tags=item.get("tags", []),
                    menu=None,
                )
                full_redraw = True
            elif len(args) > 1 and not is_int(args[1]):
                state = replace(state, menu=args[1])
                if args[1] in ("seasons", "episodes", "episode"):
                    allow_edit = False
            else:
                state = replace(state, menu=None)
        elif args[0] == "tags":
            state = replace(state, tags=[], menu="tags")
        elif args[0] == "addtag":
            state = replace(state, tags=[*state.tags, args[1]])
        elif args[0] == "remtag":
            state = replace(state, tags=[t for t in state.tags if t != args[1]])
        elif args[0] == "path":
            state = replace(state, menu="path")
        elif args[0] == "selectpath":
            path = self.get_root_folder(args[1])
            state = replace(state, root_folder=path, menu="add")
        elif args[0] == "quality":
            state = replace(state, menu="quality")
        elif args[0] == "selectquality":
            quality_profile = self.get_quality_profile(args[1])
            state = replace(state, quality_profile=quality_profile, menu="add")
        elif args[0] == "language":
            state = replace(state, menu="language")
        elif args[0] == "selectlanguage":
            language_profile = self.get_language_profile(args[1])
            state = replace(state, language_profile=language_profile, menu="add")
        elif args[0] == "addmenu":
            state = replace(state, menu="add")
        elif args[0] == "episode":
            state = replace(state, menu="episode")

        return self.create_message(
            state, full_redraw=full_redraw, allow_edit=allow_edit
        )

    @clear
    @callback(cmds=["add"])
    @sessionState(clear=True)
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_add(self, update, context, args, state):
        result = self.add(
            item=state.items[state.index],
            quality_profile_id=state.quality_profile.get("id", 0),
            language_profile_id=state.language_profile.get("id", 0),
            root_folder_path=state.root_folder.get("path", ""),
            tags=state.tags,
            options={
                "addOptions": {
                    "searchForMissingEpisodes": args[1] == "search",
                    "monitor": "all",
                }
            },
        )
        if not result:
            return Response(caption="Seems like something went wrong...")

        return Response(caption="Series updated!" if state.items[state.index].get("id") 
                                    else "Series added!")

    @clear
    @callback(cmds=["cancel"])
    @sessionState(clear=True)
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_cancel(self, update, context, args, state):
        return Response(caption="Search canceled!")

    @clear
    @callback(cmds=["remove"])
    @sessionState(clear=True)
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_remove(self, update, context, args, state):
        self.remove(id=state.items[state.index].get("id"))
        return Response(caption="Series removed!")
    
    @repaint
    @callback(cmds=["seasons", "episodes", "episode"])
    @sessionState()
    @authorized(min_auth_level=AuthLevels.USER.value)
    async def clbk_seasons(self, update, context, args, state):
        if not state.items:
            return Response(
                caption="No series found",
                state=state,
            )

        items = state.items
        item = items[state.index]

        if args[0] == "seasons":
            state = replace(state, menu="seasons")
            caption = self.media_caption(item)

        elif args[0] == "episodes":
            state = replace(state, menu="episodes")
            seasonNumber = args[1] if len(args) > 1 else item.get("selectedSeasonNumber")
            item["selectedSeasonNumber"] = seasonNumber
            caption = self.media_caption(item)
            caption += f'\n\nSeason {seasonNumber}'

        elif args[0] == "episode":
            state = replace(state, menu="episode")

            seasonNumber =  args[1] if len(args) > 1 else item.get("selectedSeasonNumber")
            episodeNumber = args[2] if len(args) > 2 else item.get("selectedEpisodeNumber")
            episodeId =     args[3] if len(args) > 3 else item.get("selectedEpisodeId")

            item["selectedSeasonNumber"] = seasonNumber
            item["selectedEpisodeNumber"] = episodeNumber
            item["selectedEpisodeId"] = episodeId

            caption = self.episode_caption(item)

        keyboard_markup = self.keyboard(state, allow_edit=False)
        
        return Response(
            caption=caption,
            reply_markup=keyboard_markup,
            state=state,
        )
    
    def episode_caption(self, item):
        episodeId = item.get("selectedEpisodeId")
        episode = self.get_episode(episodeId)

        caption = self.media_caption(item, overview=False)
        caption += f'\nSeason {episode["seasonNumber"]}, Ep. {episode["episodeNumber"]} - {episode["title"]}'
        caption+= f'\n\n{episode["overview"]}'

        return caption
    
    def get_btn_seasons(self, seriesId) -> List:
        return [
            [
                Button(
                    f'Season {p.get("seasonNumber", "-")} ({p.get("statistics").get("episodeFileCount", "0")} / {p.get("statistics").get("totalEpisodeCount")})',
                    self.get_clbk("episodes", p.get("seasonNumber")),
                )
            ]
            for p in self.get_seasons(seriesId)
        ]
    
    def get_btn_episodes(self, seriesId, seasonNumber) -> List:
        return [
            [
                Button(
                    f'Ep. {p.get("episodeNumber", "-")} - {p.get("title", "Untitled")}',
                    self.get_clbk("episode", seasonNumber, p.get("episodeNumber"), p.get("id")),
                )
            ]
            for p in self.get_episodes(seriesId, seasonNumber)
        ]

    def get_seasons(self, seriesId) -> List:
        series = self.request(f'series/{seriesId}', fallback=[])

        if len(series) > 0:
            return series.get('seasons')
        else:
            return series
    
    def get_episodes(self, seriesId, seasonNumber) -> List:
        params = {'seriesId': seriesId, 'seasonNumber': seasonNumber}
        episodes = self.request('episode', params=params, fallback=[])
        return episodes
    
    def get_episode(self, episodeId):
        return self.request(f'episode/{episodeId}', fallback=[])