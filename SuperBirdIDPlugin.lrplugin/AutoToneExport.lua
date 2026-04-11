--[[
    SuperPicky - Auto Tone + Export

    Applies autoTone to selected photos and exports as TIFF.
    Triggered from: Library → Plugin Extras → SuperPicky - Auto Tone + Export
]]

local LrApplication = import 'LrApplication'
local LrDevelopController = import 'LrDevelopController'
local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrProgressScope = import 'LrProgressScope'
local LrExportSession = import 'LrExportSession'
local LrPathUtils = import 'LrPathUtils'
local LrFileUtils = import 'LrFileUtils'
local LrFunctionContext = import 'LrFunctionContext'

LrTasks.startAsyncTask(function()
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()

    if #photos == 0 then
        LrDialogs.message(
            "SuperPicky",
            "Please select photos to process first.",
            "warning"
        )
        return
    end

    -- Ask for output directory
    local outputDir = LrDialogs.runOpenPanel({
        title = "Select TIFF Export Directory",
        canChooseDirectories = true,
        canChooseFiles = false,
        allowsMultipleSelection = false,
    })

    if not outputDir or #outputDir == 0 then
        return
    end
    outputDir = outputDir[1]

    local progress = LrProgressScope({
        title = "SuperPicky - Auto Tone + Export",
    })
    progress:setCancelable(true)

    local processed = 0
    local failed = 0

    -- Phase 1: Apply Auto Tone to each photo
    for i, photo in ipairs(photos) do
        if progress:isCanceled() then break end
        progress:setPortionComplete(i - 1, #photos * 2)  -- *2 for tone + export
        progress:setCaption(
            string.format("Auto Tone %d/%d: %s",
                i, #photos,
                photo:getFormattedMetadata("fileName"))
        )

        catalog:withWriteAccessDo("AutoTone", function()
            catalog:setSelectedPhotos(photo, {photo})
        end)

        -- Switch to Develop and apply autoTone
        LrDevelopController.revealPanel("adjustPanel")
        LrTasks.sleep(0.3)  -- Allow UI to update
        LrDevelopController.autoTone()
        LrTasks.sleep(0.2)

        processed = processed + 1
        LrTasks.yield()
    end

    if progress:isCanceled() then
        progress:done()
        LrDialogs.message("SuperPicky",
            string.format("Cancelled. Auto Tone applied to %d photos.",
                processed),
            "info")
        return
    end

    -- Phase 2: Batch export as TIFF
    progress:setCaption("Exporting TIFF files...")

    local exportSettings = {
        LR_export_destinationType = "specificFolder",
        LR_export_destinationPathPrefix = outputDir,
        LR_export_useSubfolder = false,

        LR_format = "TIFF",
        LR_tiff_compressionMethod = "compressionMethod_None",
        LR_tiff_bitDepth = 16,

        LR_export_colorSpace = "AdobeRGB",
        LR_size_doNotEnlarge = true,

        LR_removeLocationMetadata = false,
        LR_metadata_keywordOptions = "flat",
        LR_embeddedMetadataOption = "all",

        LR_reimportExportedPhoto = false,
    }

    LrFunctionContext.callWithContext("export", function(context)
        local exportSession = LrExportSession({
            photosToExport = photos,
            exportSettings = exportSettings,
        })

        local numRendered = 0
        for _, rendition in exportSession:renditions() do
            if progress:isCanceled() then break end

            local success, path = rendition:waitForRender()
            numRendered = numRendered + 1
            progress:setPortionComplete(
                #photos + numRendered, #photos * 2
            )

            if not success then
                failed = failed + 1
            end
        end
    end)

    progress:done()

    LrDialogs.message("SuperPicky",
        string.format(
            "Done!\n\nAuto Tone applied: %d photos\nTIFF exported to: %s\nFailed: %d",
            processed, outputDir, failed
        ),
        "info"
    )
end)
