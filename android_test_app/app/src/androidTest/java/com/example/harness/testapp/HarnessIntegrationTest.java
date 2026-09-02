package com.example.harness.testapp;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

@RunWith(AndroidJUnit4.class)
public class HarnessIntegrationTest {

    @Test
    public void testApplicationLaunch() {
        Context context = ApplicationProvider.getApplicationContext();
        Intent intent = context.getPackageManager().getLaunchIntentForPackage("com.example.harness.testapp");
        assertNotNull("Launch intent should not be null", intent);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK);
        context.startActivity(intent);
        assertTrue(true); // If we reached here without crashing, we consider it a success for this minimal test
    }

    @Test
    public void testPackageManager() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        PackageManager pm = context.getPackageManager();
        assertNotNull("PackageManager should not be null", pm);
        
        // Verify we can find our own package
        assertNotNull(pm.getPackageInfo("com.example.harness.testapp", 0));
    }

    @Test
    public void testBasicSystemInteraction() {
        // Assert we are running in an Android environment
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertEquals("com.example.harness.testapp", context.getPackageName());
    }

    @Test
    public void testDeviceEnvironment() {
        // Verify we can read standard Android system properties safely
        String manufacturer = Build.MANUFACTURER;
        String model = Build.MODEL;
        assertNotNull("Manufacturer should not be null", manufacturer);
        assertNotNull("Model should not be null", model);
        assertTrue("Model string should not be empty", model.length() > 0);
    }
}
